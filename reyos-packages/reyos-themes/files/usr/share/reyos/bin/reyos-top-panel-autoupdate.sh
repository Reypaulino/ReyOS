#!/bin/bash
# Runs at login (etc/xdg/autostart/reyos-top-panel-update.desktop). When a
# package update ships a new top-bar layout (panels/top-panel.version), rebuild
# the top bar once for this user, so existing installs get it from a plain
# update. Fresh accounts are left to reyos-apply-branding.sh, which builds the
# panels and writes the same marker; accounts that unlocked panel editing are
# never touched.
VERSION_FILE=/usr/share/reyos/panels/top-panel.version
MARK="$HOME/.config/reyos-top-panel-version"
[ -f "$HOME/.config/reyos-branding-applied" ] || exit 0
[ -f "$HOME/.config/reyos-panel-editing-requested" ] && exit 0
want=$(cat "$VERSION_FILE" 2>/dev/null)
[ -n "$want" ] || exit 0
[ "$(cat "$MARK" 2>/dev/null)" = "$want" ] && exit 0
for _ in $(seq 1 60); do
  qdbus6 org.kde.plasmashell /PlasmaShell >/dev/null 2>&1 && break
  sleep 1
done
sleep 5
/usr/share/reyos/bin/reyos-apply-top-panel.sh && printf '%s\n' "$want" > "$MARK"
