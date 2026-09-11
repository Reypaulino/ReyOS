#!/bin/bash
# Live-ISO-only recovery flow, triggered by booting the "ReyOS Recovery"
# boot-menu entry (reyos.recovery=1 on the kernel cmdline) instead of the
# normal install-medium entry -- makes "recover it without fear" literally
# true: restore an existing install's Timeshift snapshot from the live
# medium, without needing to reinstall from scratch first. Reuses
# Timeshift's own restore GUI (which already supports targeting any
# selected disk, not just the running system) rather than reimplementing
# snapshot discovery/restore here.
grep -qw "reyos.recovery" /proc/cmdline || exit 0

# Calamares and reyos-welcome both autostart unconditionally on any live
# boot -- neither one knows about this recovery mode (Calamares' autostart
# ships with the upstream calamares package itself, not something ReyOS
# has a .desktop file of its own to suppress), so shut them down instead
# of trying to prevent them from launching in the first place. Autostart
# timing across a live session is racy (documented elsewhere in this
# repo), so keep retrying for a while rather than a single pkill attempt.
(
  for _ in $(seq 1 20); do
    pkill -x calamares 2>/dev/null
    pkill -f "/usr/share/reyos/welcome/main.py" 2>/dev/null
    sleep 1
  done
) &

exec timeshift-launcher
