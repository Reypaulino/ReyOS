#!/bin/bash
# /etc/lsb-release is owned directly by the lsb-release package (confirmed
# via pacman -Qo), so shipping our own copy at that exact path would be a
# real pacman file conflict -- same pattern as reyos-calamares's overrides.
# Real bug this fixes: neofetch (and anything else parsing lsb-release)
# read DISTRIB_DESCRIPTION="Arch Linux" from the stock file and showed that
# instead of ReyOS, even though /etc/os-release was already correctly
# branded -- neofetch prefers lsb-release when both exist.
set -e -u
install -Dm644 /etc/reyos/lsb-release /etc/lsb-release
