#!/bin/bash
# Live-session-only wallpaper fix. reyos-welcome (which normally triggers
# reyos-apply-branding.sh on a real install) refuses to run at all on the
# live ISO, so nothing else ever sets the desktop/lock-screen wallpaper here
# -- confirmed via screenshot: the Calamares installer ran against the stock
# default Breeze wallpaper the whole way through, never the ReyOS one.
for _ in $(seq 1 30); do
  qdbus6 org.kde.plasmashell 2>/dev/null && break
  sleep 1
done

qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
var d = desktops();
for (i = 0; i < d.length; i++) {
    d[i].wallpaperPlugin = "org.kde.image";
    d[i].currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d[i].writeConfig("Image", "file:///usr/share/backgrounds/reyos-wallpaper.jpg");
}
' >/dev/null 2>&1

kwriteconfig6 --file kscreenlockerrc --group Greeter --group Wallpaper --group org.kde.image --group General --key Image "file:///usr/share/backgrounds/reyos-wallpaper.jpg"
