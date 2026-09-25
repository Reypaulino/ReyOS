#!/bin/bash
# Moves Control Center's applyLook()-recolored system files from their /tmp
# staging paths into their real root-owned locations. A fixed, no-argument
# script (not a raw "sudo cp"/"sudo bash -c <built string>") specifically so
# the NOPASSWD sudoers rule granting it can name this exact path -- matches
# reyos-welcome/enable-multilib.sh's precedent (see docs/whats-next.md and
# shellprocess_sudoers_reyos_menu.conf's own comments on why a raw cp/chown
# wildcard is never granted). Every pair below is a no-op if its /tmp source
# doesn't exist, so a Look switch that only changed some of these targets
# still runs this once and safely skips the rest.
set -f

copy_if_present() {
  [ -f "$1" ] && cp "$1" "$2"
}

copy_if_present /tmp/reyos-look-gear-16.svg /usr/share/icons/ReyOS/apps/16/preferences-system.svg
copy_if_present /tmp/reyos-look-gear-32.svg /usr/share/icons/ReyOS/apps/32/preferences-system.svg
copy_if_present /tmp/reyos-look-gear-48.svg /usr/share/icons/ReyOS/apps/48/preferences-system.svg
copy_if_present /tmp/reyos-look-launcher.svg /usr/share/icons/hicolor/scalable/apps/reyos-launcher.svg
copy_if_present /tmp/reyos-look-launcher.png /usr/share/icons/hicolor/256x256/apps/reyos-launcher.png
copy_if_present /tmp/reyos-look-control-center.svg /usr/share/icons/hicolor/scalable/apps/reyos-control-center.svg
copy_if_present /tmp/reyos-look-browser.svg /usr/share/icons/hicolor/scalable/apps/reyos-browser.svg
copy_if_present /tmp/reyos-look-reader.svg /usr/share/icons/hicolor/scalable/apps/reyos-reader.svg
copy_if_present /tmp/reyos-look-distrobox-gui.svg /usr/share/icons/hicolor/scalable/apps/reyos-distrobox-gui.svg
copy_if_present /tmp/reyos-look-browser-Main.qml /usr/share/reyos/browser/qml/Main.qml
copy_if_present /tmp/reyos-look-browser-home.html /usr/share/reyos/browser/home.html

rm -f /tmp/reyos-look-gear-16.svg /tmp/reyos-look-gear-32.svg /tmp/reyos-look-gear-48.svg \
      /tmp/reyos-look-launcher.svg /tmp/reyos-look-launcher.png \
      /tmp/reyos-look-control-center.svg /tmp/reyos-look-browser.svg \
      /tmp/reyos-look-reader.svg /tmp/reyos-look-distrobox-gui.svg \
      /tmp/reyos-look-browser-Main.qml /tmp/reyos-look-browser-home.html
