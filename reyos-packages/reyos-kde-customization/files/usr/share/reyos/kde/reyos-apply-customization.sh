#!/usr/bin/env bash
set -euo pipefail

qdbus_cmd="$(command -v qdbus6 || command -v qdbus)"
[ -n "$qdbus_cmd" ] || exit 1

# Older ReyOS themes enabled an Edit Mode guard. Disable it so this optional
# desktop layout stays fully user-customizable.
systemctl --user disable --now reyos-edit-mode-guard.service >/dev/null 2>&1 || true

"$qdbus_cmd" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
var ds = desktops();
for (var i = 0; i < ds.length; ++i) {
    ds[i].wallpaperPlugin = "org.kde.image";
    ds[i].currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    ds[i].writeConfig("Image", "file:///usr/share/backgrounds/reyos-wallpaper.jpg");
}

var existing = panels();
for (var p = existing.length - 1; p >= 0; --p) {
    existing[p].remove();
}

var top = new Panel;
top.location = "top";
top.height = 30;
top.floating = false;
top.immutability = 1;
top.addWidget("org.reyos.workspacedots");
top.addWidget("org.kde.plasma.panelspacer");
var clock = top.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", true);
clock.writeConfig("dateDisplayFormat", "Custom");
clock.writeConfig("customDateFormat", "ddd, MMM d");
top.addWidget("org.kde.plasma.panelspacer");
top.addWidget("org.kde.plasma.systemtray");
top.addWidget("org.kde.plasma.lock_logout");

var bottom = new Panel;
bottom.location = "bottom";
bottom.height = 40;
bottom.floating = false;
bottom.immutability = 1;
var launcher = bottom.addWidget("org.kde.plasma.kickoff");
launcher.currentConfigGroup = ["General"];
launcher.writeConfig("icon", "reyos-launcher");
bottom.addWidget("org.kde.plasma.icontasks");
'
touch "$HOME/.config/reyos-kde-customization-applied"
