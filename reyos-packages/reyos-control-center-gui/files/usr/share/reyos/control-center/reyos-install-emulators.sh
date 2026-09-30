#!/bin/sh
# Installs RetroArch plus the libretro cores for the requested systems.
# Run by Control Center's Gaming page through pkexec (one admin-password
# prompt per install), the same pattern as reyos-manage-users.sh: a fixed
# helper that only accepts known system ids and maps them to a fixed package
# list itself, so it can never be used to install arbitrary packages as root.
# Every package comes from Arch's official [extra] repo.
#
# Usage: reyos-install-emulators.sh <system-id>...
set -eu

[ "$#" -gt 0 ] || { echo "usage: $0 <system-id>..." >&2; exit 2; }

pkgs="retroarch retroarch-assets-ozone libretro-core-info"
for system in "$@"; do
    case "$system" in
        nes)      pkgs="$pkgs libretro-nestopia" ;;
        snes)     pkgs="$pkgs libretro-snes9x" ;;
        gb)       pkgs="$pkgs libretro-gambatte" ;;
        gba)      pkgs="$pkgs libretro-mgba" ;;
        genesis)  pkgs="$pkgs libretro-genesis-plus-gx" ;;
        n64)      pkgs="$pkgs libretro-mupen64plus-next" ;;
        psx)      pkgs="$pkgs libretro-beetle-psx" ;;
        psp)      pkgs="$pkgs libretro-ppsspp" ;;
        nds)      pkgs="$pkgs libretro-melonds" ;;
        gamecube) pkgs="$pkgs libretro-dolphin" ;;
        *) echo "unknown system: $system" >&2; exit 2 ;;
    esac
done

echo "\$ pacman -Sy --noconfirm"
pacman -Sy --noconfirm
echo "\$ pacman -S --needed --noconfirm $pkgs"
# $pkgs is built only from the fixed names above; word splitting is intended.
# shellcheck disable=SC2086
exec pacman -S --needed --noconfirm $pkgs
