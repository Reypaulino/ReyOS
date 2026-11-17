#!/usr/bin/env bash
# Installs rebuild.sh and its daily systemd user timer on the machine that
# holds the ReyOS signing key and ~/reyva-flatpak-work/site. Re-run after
# rebuild.sh changes.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
install -Dm755 "$HERE/rebuild.sh" "$HOME/.local/libexec/reyos/reyva-flatpak-rebuild.sh"
install -Dm644 "$HERE/systemd/reyva-flatpak-rebuild.service" "$HOME/.config/systemd/user/reyva-flatpak-rebuild.service"
install -Dm644 "$HERE/systemd/reyva-flatpak-rebuild.timer" "$HOME/.config/systemd/user/reyva-flatpak-rebuild.timer"
systemctl --user daemon-reload
systemctl --user enable --now reyva-flatpak-rebuild.timer
systemctl --user list-timers reyva-flatpak-rebuild.timer --no-pager
echo "Log: ${XDG_STATE_HOME:-$HOME/.local/state}/reyva-rebuild/rebuild.log"
