#!/bin/bash
# Live-session-only taskbar. The ReyOS panels are built by reyos-apply-branding.sh
# (triggered by reyos-welcome), which never runs on the live ISO, and the ReyOS
# Plasma theme ships no default layout -- so the live desktop was a bare
# wallpaper: closing the installer left nothing to click, no way to reopen it,
# and no way to try ReyOS before installing.
grep -qE "archisobasedir=|archisolabel=" /proc/cmdline || exit 0

# A live session has no password the user knows, so never lock it on idle.
kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock false
kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockOnResume false

for _ in $(seq 1 30); do
  qdbus6 org.kde.plasmashell 2>/dev/null && break
  sleep 1
done

qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript '
if (panels().length > 0) { "has-panel" } else {
var b = new Panel;
b.location = "bottom";
b.height = 40;
b.floating = false;
var l = b.addWidget("org.kde.plasma.kickoff");
l.currentConfigGroup = ["General"];
l.writeConfig("icon", "reyos-launcher");
var it = b.addWidget("org.kde.plasma.icontasks");
it.currentConfigGroup = ["General"];
// One pin only: several pins rendered just the first in the live session (checked on a
// live VM), and the start menu already lists every other app.
it.writeConfig("launchers", "applications:reyos-install.desktop");
b.addWidget("org.kde.plasma.systemtray");
b.addWidget("org.kde.plasma.digitalclock");
"created" }
' >/dev/null 2>&1
