#!/bin/bash
# Rebuild only the ReyOS top bar (layout in /usr/share/reyos/panels/top-panel.js)
# for the current user, leaving the bottom dock and its pinned apps alone.
# New accounts get it from reyos-apply-branding.sh; run this on an existing one.
JS=/usr/share/reyos/panels/top-panel.js
CONFIG_FILE="$HOME/.config/plasma-org.kde.plasma.desktop-appletsrc"
qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript \
  "var e=panels(); for (var p=e.length-1; p>=0; --p) { if (e[p].location == 'top') e[p].remove(); } $(cat "$JS")" || exit 1
sleep 3
# Translucent like the rest of ReyOS (opacityMode only sticks through the config file)
for id in $(awk '/^\[Containments\]\[[0-9]+\]$/{gsub(/[^0-9]/,"",$0); id=$0} /^location=3$/{print id}' "$CONFIG_FILE"); do
  kwriteconfig6 --file plasma-org.kde.plasma.desktop-appletsrc --group Containments --group "$id" --group General --key opacityMode Translucent
done
kquitapp6 plasmashell >/dev/null 2>&1 || true
(setsid kstart plasmashell >/dev/null 2>&1 &)
