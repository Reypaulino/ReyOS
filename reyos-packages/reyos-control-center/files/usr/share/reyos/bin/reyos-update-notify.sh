#!/bin/bash
#
# Desktop nudge, run once per graphical login, telling the user to open
# ReyOS System Tools when packages haven't been updated in a while.
# Reads the same ~/.last_pkg_update stamp reyos-system-menu.sh writes
# after a successful "Install updates" / "Full update" run — kept in
# sync manually since the threshold lives in two separate scripts.

UPDATE_STAMP="$HOME/.last_pkg_update"
UPDATE_INTERVAL_DAYS=3

if [ -f "$UPDATE_STAMP" ]; then
  upd_days=$(( ($(date +%s) - $(stat -c %Y "$UPDATE_STAMP")) / 86400 ))
else
  upd_days=999
fi

[ "$upd_days" -lt "$UPDATE_INTERVAL_DAYS" ] && exit 0

if [ "$upd_days" -ge 999 ]; then
  body="No record of a recent update."
else
  body="Last update was ${upd_days} day(s) ago."
fi

# Backgrounded: -A/--action implies --wait, which blocks until the
# notification is clicked or times out -- fine to let that run
# detached rather than holding up the rest of autostart.
(
  command -v notify-send &>/dev/null || exit 0
  action=$(notify-send \
    --icon=system-software-update \
    --urgency=normal \
    --app-name="ReyOS" \
    --action="open=Open Updates" \
    "ReyOS updates available" \
    "${body}")
  if [ "$action" = "open" ]; then
    # Same launch pattern reyos-welcome's openControlCenterUpdates()
    # uses: kill any stale Control Center window first so this action
    # always shows a fresh one, not a leftover from an earlier session.
    pkill -f "python3 /usr/share/reyos/control-center/main.py" 2>/dev/null
    REYOS_CC_INITIAL_PAGE="UpdatesPage.qml" setsid python3 \
      /usr/share/reyos/control-center/main.py &
  fi
) &
disown
