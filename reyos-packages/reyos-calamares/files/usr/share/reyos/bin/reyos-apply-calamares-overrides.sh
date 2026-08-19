#!/bin/bash
# cachyos-calamares ships every /etc/calamares/modules/*.conf file we need
# to customize directly (not under /usr/share/calamares/ like settings.conf,
# which Calamares itself treats as an overridable default) -- so our own
# copies of those same paths would be real pacman file conflicts if both
# packages installed them in the same transaction (confirmed for users.conf:
# this happens during a fresh pacstrap install, not just an incremental
# upgrade). Shipping our versions as staged files + copying them over here,
# via a hook, sidesteps the conflict entirely instead of fighting pacman's
# file-ownership tracking.
set -e -u
for f in users.conf partition.conf unpackfs.conf bootloader.conf grubcfg.conf; do
    install -Dm644 "/usr/share/reyos/calamares-overrides/$f" "/etc/calamares/modules/$f"
done
