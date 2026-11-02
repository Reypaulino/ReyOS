#!/usr/bin/env bash
# Installs every reyos-* package on top of one Arch Linux Archive snapshot and
# checks that the apps' Python imports and QML modules still load. Run as root
# in a throwaway Arch container:  smoke-test.sh 2026/10/07
#
# Exit status (the workflow reports each one differently):
#   0   passed
#   75  not validated: downloads from archive.archlinux.org kept timing out or
#       dropping after every retry. Says nothing about the snapshot itself.
#   1   failed: a package, signature, dependency, import or QML problem
#   2   bad date, or the snapshot doesn't exist
#
# Downloads are retried; nothing else is. Every package comes from the one
# snapshot date (and reyos-local), never from Arch's live mirrors.
set -euo pipefail

DATE=${1:?usage: smoke-test.sh YYYY/MM/DD}
[[ $DATE =~ ^[0-9]{4}/[0-9]{2}/[0-9]{2}$ ]] || { echo "bad date: $DATE (want YYYY/MM/DD)" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
SERVER="https://archive.archlinux.org/repos/$DATE/\$repo/os/\$arch"
# Overridable for tests/test_stable_snapshot_smoke.py only.
CONF=${SMOKE_PACMAN_CONF:-/etc/pacman.conf}
SUMMARY=${SMOKE_SUMMARY:-smoke-summary.md}
ATTEMPTS=${SMOKE_ATTEMPTS:-4}
DELAY=${SMOKE_RETRY_DELAY:-30}   # doubles after each failed attempt: 30, 60, 120 s
LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

# Network trouble a later attempt can get past. Anything else (404, signature,
# checksum, corrupted package, dependency or file conflicts, imports, QML) is a
# real failure and is never retried; FATAL wins when both show up.
TRANSIENT='Operation too slow|Operation timed out|Connection timed out|Could not resolve host|Resolving timed out|Failed to connect|Connection reset|Connection refused|Recv failure|SSL connection timeout|transfer closed|HTTP/2 stream|returned error: 5[0-9][0-9]|Empty reply from server'
FATAL='returned error: 404|signature|checksum|corrupted|could not satisfy dependencies|unable to satisfy dependency|unresolvable package conflicts|conflicting files|are in conflict|target not found|invalid PGP|unknown trust|key .* could not be'

summary() { printf '%s\n' "$@" >> "$SUMMARY"; }
: > "$SUMMARY"
summary "## Stable snapshot check: \`$DATE\`" ""

failed() {  # failed LABEL RC ATTEMPT
    summary "**Result: FAILED** in \"$1\" (exit $2, attempt $3). Not a download timeout, so not retried." "" '```'
    grep -v '^ *$' "$LOG" | tail -n 25 >> "$SUMMARY" || true
    summary '```'
    echo "::error::$1 failed"
    exit 1
}
not_validated() {  # not_validated LABEL ATTEMPTS
    summary "**Result: NOT TESTED** (download failure, not validated). \"$1\" hit download timeouts on $2 attempt(s). This says nothing about whether the snapshot works with ReyOS: run the check again for the same date." "" '```'
    grep -E "$TRANSIENT" "$LOG" | tail -n 20 >> "$SUMMARY" || true
    summary '```'
    echo "::error::$1: archive downloads still failing after $2 attempt(s); snapshot not validated"
    exit 75
}
transient() { ! grep -Eq "$FATAL" "$LOG" && grep -Eq "$TRANSIENT" "$LOG"; }
run() { set +e; "$@" 2>&1 | tee "$LOG"; local rc=${PIPESTATUS[0]}; set -e; return "$rc"; }

# retry LABEL CMD...: a download step, run up to $ATTEMPTS times while its
# failures are only transient download errors.
retry() {
    local label=$1 n=1 wait=$DELAY rc
    shift
    while :; do
        rc=0; run "$@" || rc=$?
        [ "$rc" = 0 ] && return 0
        transient || failed "$label" "$rc" "$n of $ATTEMPTS"
        [ "$n" -lt "$ATTEMPTS" ] || not_validated "$label" "$ATTEMPTS"
        echo "::warning::$label: download timeout (attempt $n of $ATTEMPTS), retrying in ${wait}s"
        summary "- \"$label\" attempt $n: $(grep -Eo "$TRANSIENT" "$LOG" | head -n 1), retried after ${wait}s"
        sleep "$wait"
        n=$((n + 1)) wait=$((wait * 2))
    done
}
# once LABEL CMD...: an install step working from the download cache; never
# retried. A download error here still isn't evidence against the snapshot.
once() {
    local label=$1 rc=0
    shift
    run "$@" || rc=$?
    [ "$rc" = 0 ] && return 0
    transient && not_validated "$label" 1
    failed "$label" "$rc" 1
}

# The snapshot must exist (404: bad date, exit 2); no answer at all is retried.
n=1 wait=$DELAY
while :; do
    code=$(curl -sI -o /dev/null -w '%{http_code}' -m 30 "https://archive.archlinux.org/repos/$DATE/core/os/x86_64/core.db") || true
    case $code in
        200) break ;;
        404) echo "snapshot $DATE does not exist on archive.archlinux.org" >&2
             summary "**Result: FAILED**: snapshot \`$DATE\` does not exist on the archive."
             exit 2 ;;
    esac
    echo "error: archive.archlinux.org answered '$code' for $DATE (Connection timed out or failed)" | tee "$LOG"
    [ "$n" -lt "$ATTEMPTS" ] || not_validated "Check that the snapshot exists" "$ATTEMPTS"
    sleep "$wait"
    n=$((n + 1)) wait=$((wait * 2))
done

cat > "$CONF" <<EOF
[options]
HoldPkg = pacman glibc
Architecture = auto
# archive.archlinux.org is a single server; with 5 parallel downloads the
# 2026/10/31 check stalled on it. Stalls are retried; 3 keeps fewer in flight.
ParallelDownloads = 3
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional
NoExtract = usr/share/help/* usr/share/doc/* usr/share/man/*
# Docker creates these itself; the import checks don't need reyos-base's copies.
NoExtract = etc/hostname etc/os-release

[reyos-local]
SigLevel = Required
Server = https://reypaulino.github.io/ReyOS/
Server = https://github.com/Reypaulino/ReyOS/releases/download/reyos-drivers

[core]
Server = $SERVER

[extra]
Server = $SERVER

[multilib]
Server = $SERVER
EOF

pacman-key --init >/dev/null
pacman-key --populate archlinux >/dev/null
pacman-key --add "$HERE/reyos-signing-key.asc" >/dev/null
pacman-key --lsign-key 9A17D49EE3929AC6402337FA66E4085621026272 >/dev/null

# Download first (retried; what's already in the cache isn't fetched again),
# then install from the cache, which checks every signature and dependency.
echo "::group::Upgrade the container to snapshot $DATE"
retry "Download snapshot $DATE" pacman --config "$CONF" -Syyuuw --noconfirm
once "Upgrade to snapshot $DATE" pacman --config "$CONF" -Suu --noconfirm
echo "::endgroup::"

# reyos-* only: reyos-local also carries NVIDIA's 580 driver (nvidia-580xx-*,
# from the reyos-drivers release), which a container can't test and which
# conflicts with Arch's nvidia-utils; it broke the 2026/10/24 check.
mapfile -t PKGS < <(pacman --config "$CONF" -Slq reyos-local | grep '^reyos-')
[ "${#PKGS[@]}" -gt 0 ] || { summary "**Result: FAILED**: reyos-local lists no reyos-* packages."; exit 1; }
echo "::group::Install ${#PKGS[@]} reyos-* packages"
retry "Download ${#PKGS[@]} reyos-* packages" pacman --config "$CONF" -Sw --needed --noconfirm "${PKGS[@]}"
once "Install ${#PKGS[@]} reyos-* packages" pacman --config "$CONF" -S --needed --noconfirm \
    --overwrite /etc/hostname --overwrite /etc/os-release "${PKGS[@]}"
echo "::endgroup::"

export QT_QPA_PLATFORM=offscreen
rc=0; run python3 "$HERE/check-imports.py" /usr/share/reyos || rc=$?
if [ "$rc" != 0 ]; then
    summary "**Result: FAILED**: imports/QML check (exit $rc)." "" '```'
    tail -n 30 "$LOG" >> "$SUMMARY"
    summary '```'
    exit 1
fi
summary "**Result: passed.** ${#PKGS[@]} reyos-* packages installed on \`$DATE\`; imports and QML modules loaded."
