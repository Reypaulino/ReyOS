#!/bin/bash
# Kicks the user straight back out of Plasma's Edit Mode the instant it's
# entered. This is a workaround, not a proper fix -- researched and
# confirmed (2026-08-08) that Plasma 6 doesn't gate Corona.editMode through
# the Kiosk Action Restrictions framework (no KAuthorized check found near
# editModeChanged in libPlasmaQuick's symbol table), and per-containment
# immutability=3 already genuinely blocks "Add or Manage Widgets" but not
# the full Edit Mode overlay once entered. Polls rather than reacting to a
# signal because Corona.editMode's Set calls were confirmed (via
# dbus-monitor, broad path filter) to never emit a PropertiesChanged signal
# at all -- there's nothing to listen for.
while true; do
  state=$(qdbus6 org.kde.plasmashell /PlasmaShell org.freedesktop.DBus.Properties.Get org.kde.PlasmaShell editMode 2>/dev/null)
  if [ "$state" = "true" ]; then
    qdbus6 org.kde.plasmashell /PlasmaShell org.freedesktop.DBus.Properties.Set org.kde.PlasmaShell editMode false >/dev/null 2>&1
  fi
  sleep 0.3
done
