#!/usr/bin/env bash
# Installs every reyos-* package on top of one Arch Linux Archive snapshot and
# checks that the apps' Python imports and QML modules still load. Run as root
# in a throwaway Arch container:  smoke-test.sh 2026/10/07
set -euo pipefail

DATE=${1:?usage: smoke-test.sh YYYY/MM/DD}
[[ $DATE =~ ^[0-9]{4}/[0-9]{2}/[0-9]{2}$ ]] || { echo "bad date: $DATE (want YYYY/MM/DD)" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
SERVER="https://archive.archlinux.org/repos/$DATE/\$repo/os/\$arch"

curl -fsI "https://archive.archlinux.org/repos/$DATE/core/os/x86_64/core.db" >/dev/null \
    || { echo "snapshot $DATE does not exist on archive.archlinux.org" >&2; exit 2; }

cat > /etc/pacman.conf <<EOF
[options]
HoldPkg = pacman glibc
Architecture = auto
ParallelDownloads = 5
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional
NoExtract = usr/share/help/* usr/share/doc/* usr/share/man/*
# Docker creates these itself; the import checks don't need reyos-base's copies.
NoExtract = etc/hostname etc/os-release

[reyos-local]
SigLevel = Required
Server = https://reypaulino.github.io/ReyOS/

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

echo "::group::Upgrade the container to snapshot $DATE"
pacman -Syyuu --noconfirm
echo "::endgroup::"

mapfile -t PKGS < <(pacman -Slq reyos-local)
echo "::group::Install ${#PKGS[@]} reyos-* packages"
pacman -S --needed --noconfirm "${PKGS[@]}"
echo "::endgroup::"

export QT_QPA_PLATFORM=offscreen
python3 "$HERE/check-imports.py" /usr/share/reyos
