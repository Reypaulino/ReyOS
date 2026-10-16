#!/bin/sh
# Installs RetroArch plus the libretro cores for the requested systems.
# Run by Control Center's Gaming page through pkexec (one admin-password
# prompt per install), the same pattern as reyos-manage-users.sh: a fixed
# helper that only accepts known system ids and maps them to a fixed package
# list itself, so it can never be used to install arbitrary packages as root.
# Every package comes from Arch's official [extra] repo. PS2 and 3DS come
# from Flathub instead and are installed per-user by Control Center itself.
# "shrink" installs the game shrinking tool (chdman, from mame-tools) that
# "Add games" uses; it needs no emulator.
#
# Usage: reyos-install-emulators.sh <system-id|shrink>...
set -eu

[ "$#" -gt 0 ] || { echo "usage: $0 <system-id>..." >&2; exit 2; }

retroarch="retroarch retroarch-assets-ozone libretro-core-info libretro-shaders-slang"
pkgs=""
for system in "$@"; do
    case "$system" in
        shrink)   pkgs="$pkgs mame-tools"; continue ;;
        nes)      pkgs="$pkgs libretro-nestopia" ;;
        snes)     pkgs="$pkgs libretro-snes9x" ;;
        gb)       pkgs="$pkgs libretro-gambatte" ;;
        gba)      pkgs="$pkgs libretro-mgba" ;;
        genesis)  pkgs="$pkgs libretro-genesis-plus-gx" ;;
        dreamcast) pkgs="$pkgs libretro-flycast" ;;
        n64)      pkgs="$pkgs libretro-mupen64plus-next" ;;
        psx)      pkgs="$pkgs libretro-beetle-psx" ;;
        psp)      pkgs="$pkgs libretro-ppsspp" ;;
        nds)      pkgs="$pkgs libretro-melonds" ;;
        # dolphin-emu provides the Sys data folder (fonts, game fixes) the
        # libretro core needs but Arch's libretro-dolphin doesn't ship.
        gamecube) pkgs="$pkgs libretro-dolphin dolphin-emu" ;;
        *) echo "unknown system: $system" >&2; exit 2 ;;
    esac
    pkgs="$pkgs $retroarch"
    retroarch=""
done

# Installed together with any waiting system updates, in one transaction:
# `pacman -Sy` followed by `pacman -S <cores>` was a partial upgrade (the
# cores could need newer libraries than the installed system had).
# $pkgs is built only from the fixed names above; word splitting is intended.
if [ -x /usr/bin/reyos-channel ] && grep -q install_pkgs /usr/bin/reyos-channel; then
    echo "\$ reyos-channel install --yes$pkgs"
    # shellcheck disable=SC2086
    exec /usr/bin/reyos-channel install --yes $pkgs
fi
echo "\$ pacman -Syu --needed --noconfirm$pkgs"
# shellcheck disable=SC2086
exec pacman -Syu --needed --noconfirm $pkgs
