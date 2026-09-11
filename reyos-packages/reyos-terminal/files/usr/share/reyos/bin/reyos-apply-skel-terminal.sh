#!/bin/bash
# reyos-terminal's payload lives entirely under /etc/skel/ (fastfetch config
# + ASCII art, konsolerc, Konsole color scheme/profile). /etc/skel only gets
# copied into a home directory at account-creation time (useradd -m), so a
# package upgrade that changes these files never reaches already-existing
# accounts -- confirmed real 2026-09-09 (an ASCII-art escape-code fix landed
# in /etc/skel via a pacman upgrade but the already-created test account
# kept rendering the old broken banner until manually re-copied). This hook
# re-applies the current skel content to every real user's home directory
# on every reyos-terminal install/upgrade, so the fix actually reaches
# people instead of just new accounts.
set -u

for home in /home/*; do
    [[ -d "$home" ]] || continue
    user=$(basename "$home")
    id "$user" &>/dev/null || continue

    for rel in .config/fastfetch/config.jsonc .config/fastfetch/reyos-ascii.txt \
               .config/konsolerc .local/share/konsole/ReyOS.colorscheme \
               .local/share/konsole/ReyOS.profile; do
        src="/etc/skel/$rel"
        dest="$home/$rel"
        [[ -f "$src" ]] || continue
        install -Dm644 "$src" "$dest"
        chown "$user:$user" "$dest"
    done
done
