#!/usr/bin/env bash
# ReyOS WSL — build.sh
#
# Builds ReyOS-WSL-<version>-x86_64.wsl from scratch via pacstrap.
#
# MUST run as root on an Arch/CachyOS machine with the same pacman.conf
# already used to build the real ReyOS ISO (the ReyOS Dev VM) — this
# script deliberately reuses the host's /etc/pacman.conf rather than
# re-deriving mirrorlists/keyring from scratch, so ReyOS WSL always
# tracks the same repos/trust as the rest of the project. See
# docs/wsl.md "Build process".
#
# Usage: sudo ./build.sh [version]
#   version defaults to today's date (YYYY.MM.DD), matching reyos-iso.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-$(date +%Y.%m.%d)}"

WORK="${REYOS_WSL_WORK:-$HOME/reyos-build/wsl-work}"
ROOTFS="$WORK/rootfs"
OUT="${REYOS_WSL_OUT:-$HOME/reyos-build/wsl-out}"
ARTIFACT="$OUT/ReyOS-WSL-${VERSION}-x86_64.wsl"

# --- guardrails ------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root (sudo ./build.sh)." >&2
    exit 1
fi

for tool in pacstrap arch-chroot tar sha256sum; do
    command -v "$tool" &>/dev/null || { echo "Missing required tool: $tool (install arch-install-scripts)" >&2; exit 1; }
done

[ -f /etc/pacman.conf ] || { echo "No /etc/pacman.conf on this host — run on the ReyOS Dev VM, not here." >&2; exit 1; }

echo "== ReyOS WSL build $VERSION =="
echo "work:     $WORK"
echo "rootfs:   $ROOTFS"
echo "artifact: $ARTIFACT"

# --- clean known WSL build paths only (never anything outside $WORK/$OUT) --
cleanup_mounts() {
    # Generic on purpose: catches pacstrap's own /dev,/proc,/sys binds AND
    # the reyos-local bind-mount below, in reverse-mount order, however far
    # the script got before failing.
    local m
    while read -r m; do
        [ -n "$m" ] && umount -R "$m" 2>/dev/null || true
    done < <(findmnt -R -o TARGET -n "$ROOTFS" 2>/dev/null | tac)
}
trap cleanup_mounts EXIT

cleanup_mounts
rm -rf "$ROOTFS"
mkdir -p "$ROOTFS" "$OUT"

# arch-chroot warns "$ROOTFS is not a mountpoint" and, without this, pacman's
# disk-space check inside the chroot can't resolve the cache dir's mount
# boundary at all — every download fails with "could not determine cachedir
# mount point" / "not enough free disk space" regardless of actual free
# space. Bind-mounting the rootfs onto itself gives it a real mount boundary
# pacman can look up. Confirmed via a real failing build + real fix on the
# ReyOS Dev VM 2026-09-02 — this is not a defensive guess.
mount --bind "$ROOTFS" "$ROOTFS"

# --- bootstrap base userspace -----------------------------------------------
# `base` (Arch's own meta-package) deliberately excludes the `linux` kernel
# package — WSL supplies its own kernel, so we never pull one in here.
mapfile -t MINIMAL_PKGS < <(grep -vE '^\s*#|^\s*$' "$SCRIPT_DIR/package-lists/minimal.txt")
pacstrap -C /etc/pacman.conf -c "$ROOTFS" base "${MINIMAL_PKGS[@]}"

# --- reuse this host's pacman config/keyring/mirrors verbatim --------------
cp /etc/pacman.conf "$ROOTFS/etc/pacman.conf"
cp -a /etc/pacman.d/. "$ROOTFS/etc/pacman.d/"
arch-chroot "$ROOTFS" pacman-key --init
arch-chroot "$ROOTFS" pacman-key --populate archlinux

# --- bake in WSL-compatible reyos-* packages, if this host has them built --
# Uses the host's own [reyos-local] stanza (already in $ROOTFS/etc/pacman.conf,
# still active at this point) verbatim by bind-mounting the same absolute
# path into the chroot, rather than copying+renaming — that would leave the
# repo's existing reyos-local.db pointing at a name pacman never looks for.
LOCAL_REPO="/home/reyrubi/reyos-build/local-repo"
REYOS_WSL_PKGS=(reyos-terminal)
if [ -d "$LOCAL_REPO" ]; then
    echo "== baking in reyos-* packages from $LOCAL_REPO =="
    mkdir -p "$ROOTFS$LOCAL_REPO"
    mount --bind "$LOCAL_REPO" "$ROOTFS$LOCAL_REPO"
    arch-chroot "$ROOTFS" pacman -Sy --needed --noconfirm "${REYOS_WSL_PKGS[@]}" || \
        echo "WARNING: could not install ${REYOS_WSL_PKGS[*]} — continuing without them (not fatal, WSL image is still valid)"
    umount "$ROOTFS$LOCAL_REPO"
    rmdir -p --ignore-fail-on-non-empty "$ROOTFS$LOCAL_REPO" 2>/dev/null || true
else
    echo "No local repo at $LOCAL_REPO — shipping without pre-baked reyos-* packages."
fi

# reyos-local is a file:// path local to this build machine (known gap —
# there is no publicly hosted reyos-local repo yet, see docs/bugs.md).
# Shipping that stanza active would make pacman fail to sync on every
# other machine, so comment it out in the artifact now that baking is done;
# upstream Arch/CachyOS repos above it are unaffected and update normally.
sed -i '/^\[reyos-local\]/,/^Server/ s/^/#/' "$ROOTFS/etc/pacman.conf"

# --- ReyOS branding + WSL configuration overlay -----------------------------
cp -a "$SCRIPT_DIR/rootfs/." "$ROOTFS/"
install -Dm644 "$SCRIPT_DIR/wsl.conf" "$ROOTFS/etc/wsl.conf"
install -Dm755 "$SCRIPT_DIR/first-run/reyos-wsl-init.sh" "$ROOTFS/usr/local/bin/reyos-wsl-init"
install -d -m755 "$ROOTFS/usr/share/reyos-wsl/package-lists"
cp "$SCRIPT_DIR/package-lists/"*.txt "$ROOTFS/usr/share/reyos-wsl/package-lists/"
install -d -m755 "$ROOTFS/var/lib/reyos-wsl"

# --- locale -------------------------------------------------------------
echo "en_US.UTF-8 UTF-8" > "$ROOTFS/etc/locale.gen"
arch-chroot "$ROOTFS" locale-gen
echo "LANG=en_US.UTF-8" > "$ROOTFS/etc/locale.conf"
echo "reyos" > "$ROOTFS/etc/hostname"

# --- shrink + reset host-specific identity ----------------------------------
# (not `pacman -Scc` — it prompts for confirmation even with --noconfirm on
# this pacman version; a direct rm is simpler and always non-interactive)
rm -f "$ROOTFS/etc/machine-id"
rm -rf "$ROOTFS"/var/log/*.log "$ROOTFS"/var/cache/pacman/pkg/*

cleanup_mounts
trap - EXIT

# --- package artifact --------------------------------------------------
tar --numeric-owner --xattrs -C "$ROOTFS" -czf "$ARTIFACT" .
sha256sum "$ARTIFACT" | tee "$ARTIFACT.sha256"

echo
echo "== done =="
echo "$ARTIFACT"
echo "Install per docs/wsl.md — this only builds the artifact, it does not install/register it."
