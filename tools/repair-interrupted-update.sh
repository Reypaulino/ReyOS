#!/usr/bin/env bash
# Repairs a ReyOS install whose update was stopped half-way, so it doesn't
# boot any more. On 2026-10-20 Control Center was killed together with the
# desktop session in the middle of pacman's hooks: the old kernels were
# already removed from /boot (the EFI partition) and the new ones were never
# copied, so the boot menu had nothing to start. (reyos-update-channel
# 2026.10.19-2 runs updates as a system service so this can't happen again.)
#
# Run it as root from another Linux on the same computer -- Ubuntu next to
# ReyOS, or the ReyOS USB stick's live session:
#   sudo bash repair-interrupted-update.sh            # finds the ReyOS partition
#   sudo bash repair-interrupted-update.sh /dev/sdXN  # or name it
#   sudo bash repair-interrupted-update.sh --check    # only show what it would do
#
# It mounts ReyOS with its EFI partition as /boot, removes pacman's stale lock
# and reinstalls every package of the last update from ReyOS's own package
# cache (downloading only what isn't there), which reruns the steps that were
# cut off: kernel images and initramfs, DKMS modules, the Limine boot menu,
# icon/font/desktop caches. Your files and settings aren't touched.
set -euo pipefail

MNT=/mnt/reyos-repair
CHECK=0
DEV=""
for a in "$@"; do
    case "$a" in
        --check) CHECK=1 ;;
        /dev/*) DEV=$a ;;
        *) echo "usage: $0 [--check] [/dev/ROOT-PARTITION]" >&2; exit 2 ;;
    esac
done
[ "$(id -u)" -eq 0 ] || { echo "Run it with sudo." >&2; exit 1; }

cleanup() {
    if mountpoint -q "$MNT"; then umount -R "$MNT" 2>/dev/null || umount -lR "$MNT"; fi
}
trap cleanup EXIT

# The ReyOS root: ext4 at the top, or btrfs with ReyOS in the @ subvolume.
is_reyos() {  # is_reyos DEV -> prints the mount options to use, if it's ReyOS
    local tmp opt=""
    tmp=$(mktemp -d)
    if mount -o ro "$1" "$tmp" 2>/dev/null; then
        if grep -qs '^ID=reyos' "$tmp/etc/os-release"; then opt="defaults"
        elif grep -qs '^ID=reyos' "$tmp/@/etc/os-release"; then opt="subvol=@"
        fi
        umount "$tmp"
    fi
    rmdir "$tmp"
    [ -n "$opt" ] && echo "$opt"
}

if [ -z "$DEV" ]; then
    while read -r name fstype; do
        case "$fstype" in ext4|btrfs) ;; *) continue ;; esac
        # Not the system we're running from.
        [ "$(findmnt -n -o SOURCE /)" = "/dev/$name" ] && continue
        if is_reyos "/dev/$name" >/dev/null; then DEV=/dev/$name; break; fi
    done < <(lsblk -rno NAME,FSTYPE)
fi
[ -n "$DEV" ] || { echo "No ReyOS partition found. Name it: $0 /dev/..." >&2; exit 1; }
OPTS=$(is_reyos "$DEV") || { echo "$DEV doesn't look like ReyOS." >&2; exit 1; }
echo ":: ReyOS: $DEV ($OPTS)"

mkdir -p "$MNT"
mountpoint -q "$MNT" && { echo "$MNT is already in use." >&2; exit 1; }
mount -o "$OPTS" "$DEV" "$MNT"

# The EFI partition ReyOS mounts as /boot (from its fstab); bind it if this
# system already has it mounted (Ubuntu's /boot/efi), else mount it.
ESP_SPEC=$(awk '$2 == "/boot" && $1 !~ /^#/ {print $1}' "$MNT/etc/fstab" | head -1)
[ -n "$ESP_SPEC" ] || { echo "ReyOS's fstab has no /boot line." >&2; exit 1; }
ESP_DEV=$(findfs "$ESP_SPEC")
ESP_AT=$(findmnt -n -o TARGET -S "$ESP_DEV" | head -1 || true)
if [ -n "$ESP_AT" ]; then mount --bind "$ESP_AT" "$MNT/boot"; else mount "$ESP_DEV" "$MNT/boot"; fi
echo ":: EFI partition: $ESP_DEV as /boot"

# The last pacman transaction: every package it installed or upgraded.
LOG="$MNT/var/log/pacman.log"
start=$(grep -n '\[ALPM\] transaction started' "$LOG" | tail -1 | cut -d: -f1)
mapfile -t PKGS < <(tail -n +"$start" "$LOG" |
    sed -nE 's/.*\[ALPM\] (installed|reinstalled) ([^ ]+) \(([^ )]+)\).*/\2 \3/p;
             s/.*\[ALPM\] (upgraded|downgraded) ([^ ]+) \([^ ]+ -> ([^ )]+)\).*/\2 \3/p')
echo ":: Last update: $(sed -n "${start}p" "$LOG" | cut -c2-25), ${#PKGS[@]} packages"

FILES=() MISSING=()
for entry in "${PKGS[@]}"; do
    name=${entry% *} ver=${entry#* }
    # Only what's still installed at that version (later removals/updates win).
    [ "$(chroot "$MNT" pacman -Q "$name" 2>/dev/null | cut -d' ' -f2)" = "$ver" ] || continue
    f=$(ls "$MNT/var/cache/pacman/pkg/$name-$ver-"{x86_64,any}.pkg.tar.zst 2>/dev/null | head -1 || true)
    if [ -n "$f" ]; then FILES+=("/var/cache/pacman/pkg/${f##*/}"); else MISSING+=("$name"); fi
done
echo ":: In the package cache: ${#FILES[@]}; to download: ${#MISSING[@]} ${MISSING[*]:-}"
echo ":: On the EFI partition now: $(cd "$MNT/boot" && ls vmlinuz-* initramfs-* 2>/dev/null | tr '\n' ' ')"
[ -e "$MNT/var/lib/pacman/db.lck" ] && echo ":: pacman's lock from the stopped update is still there"

if [ "$CHECK" = 1 ]; then
    echo ":: --check: nothing changed."
    exit 0
fi

for d in dev dev/pts proc sys run; do mount --bind "/$d" "$MNT/$d"; done
[ -d /sys/firmware/efi/efivars ] && mount --bind /sys/firmware/efi/efivars "$MNT/sys/firmware/efi/efivars" || true
cp -L /etc/resolv.conf "$MNT/etc/resolv.conf" 2>/dev/null || true
rm -f "$MNT/var/lib/pacman/db.lck"

if [ ${#MISSING[@]} -gt 0 ]; then
    chroot "$MNT" pacman -Sy --noconfirm
    chroot "$MNT" pacman -S --noconfirm "${MISSING[@]}"
fi
# Reinstalling reruns each package's scriptlets and every hook they trigger.
chroot "$MNT" pacman -U --noconfirm "${FILES[@]}"

echo
missing=0
for f in vmlinuz-linux initramfs-linux.img; do
    if [ -f "$MNT/boot/$f" ]; then echo ":: /boot/$f: OK"; else echo ":: /boot/$f: MISSING"; missing=1; fi
done
for f in vmlinuz-linux-lts initramfs-linux-lts.img; do
    [ -d "$MNT/usr/lib/modules" ] && ls "$MNT"/usr/lib/modules/*-lts >/dev/null 2>&1 || continue
    if [ -f "$MNT/boot/$f" ]; then echo ":: /boot/$f: OK"; else echo ":: /boot/$f: MISSING"; missing=1; fi
done
grep -q 'vmlinuz-linux' "$MNT/boot/limine.conf" 2>/dev/null && echo ":: Limine menu: has ReyOS entries"
if [ "$missing" = 0 ]; then echo ":: Done. Restart and pick ReyOS."; else echo ":: Not fixed -- see the output above." >&2; exit 1; fi
