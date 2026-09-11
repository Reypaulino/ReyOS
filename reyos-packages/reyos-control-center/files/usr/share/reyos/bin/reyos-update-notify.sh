#!/bin/bash
#
# Desktop nudge, run once per graphical login, telling the user to open
# ReyOS System Tools when packages haven't been updated in a while.
# Reads the same ~/.last_pkg_update stamp reyos-system-menu.sh writes
# after a successful "Install updates" / "Full update" run — kept in
# sync manually since the threshold lives in two separate scripts.
#
# Reports real pending-update counts from both pacman and flatpak (not
# just "it's been a while") -- this is ReyOS's one consolidated update
# notifier, deliberately covering both sources in a single icon/popup
# rather than one per package manager. Discover's own separate notifier
# is suppressed on purpose (see the Hidden=true skel override next to
# this script's own autostart entry) so this stays the only one.
# Counts read whatever's in the local sync db already -- this never
# triggers its own `pacman -Sy` (that's a deliberate user action via
# System Tools/Control Center, not something a passive login nudge
# should do unprompted), so a count of 0 here can still be stale if
# nothing has synced recently.

UPDATE_STAMP="$HOME/.last_pkg_update"
UPDATE_INTERVAL_DAYS=3

if [ -f "$UPDATE_STAMP" ]; then
  upd_days=$(( ($(date +%s) - $(stat -c %Y "$UPDATE_STAMP")) / 86400 ))
else
  upd_days=999
fi

[ "$upd_days" -lt "$UPDATE_INTERVAL_DAYS" ] && exit 0

pacman_count=$(pacman -Qu 2>/dev/null | wc -l)
flatpak_count=0
command -v flatpak &>/dev/null && flatpak_count=$(flatpak remote-ls --updates 2>/dev/null | wc -l)

if [ "$pacman_count" -eq 0 ] && [ "$flatpak_count" -eq 0 ]; then
  if [ "$upd_days" -ge 999 ]; then
    body="No record of a recent update — check for new ones?"
  else
    body="No updates pending as of the last check, ${upd_days} day(s) ago."
  fi
else
  parts=()
  [ "$pacman_count" -gt 0 ] && parts+=("${pacman_count} system package(s)")
  [ "$flatpak_count" -gt 0 ] && parts+=("${flatpak_count} Flatpak app(s)")
  body="Updates available: $(IFS=', '; echo "${parts[*]}")."
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
