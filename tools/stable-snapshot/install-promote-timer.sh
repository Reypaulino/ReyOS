#!/usr/bin/env bash
# Installs promote.sh and its daily systemd user timer on the machine that
# holds the ReyOS signing key. Re-run after promote.sh changes.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
install -Dm755 "$HERE/promote.sh" "$HOME/.local/libexec/reyos/promote.sh"
install -Dm644 "$HERE/systemd/reyos-stable-promote.service" "$HOME/.config/systemd/user/reyos-stable-promote.service"
install -Dm644 "$HERE/systemd/reyos-stable-promote.timer" "$HOME/.config/systemd/user/reyos-stable-promote.timer"
systemctl --user daemon-reload
systemctl --user enable --now reyos-stable-promote.timer
systemctl --user list-timers reyos-stable-promote.timer --no-pager
echo "Log: ${XDG_STATE_HOME:-$HOME/.local/state}/reyos-promote/promote.log"
