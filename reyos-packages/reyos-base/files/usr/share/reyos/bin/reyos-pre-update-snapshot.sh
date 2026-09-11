#!/bin/bash
# Auto-snapshot before any system upgrade -- closes the rolling-release
# trust gap vs. atomic distros without a full immutable-image rewrite.
# A mutable Arch base + only *scheduled* Timeshift snapshots means an
# update that breaks something can land between snapshots with nothing
# to roll back to. Runs PreTransaction (before, not after) on purpose --
# a rollback target needs the pre-update state, not the just-broken one.
#
# Must never block a real update over snapshot failure: a pacman
# PreTransaction hook that exits non-zero aborts the whole transaction,
# and Timeshift not yet configured (no snapshot device chosen) is the
# normal state for a fresh install nobody has opened Backup Center on
# yet, not an error condition. Every exit path here is 0.
CONFIG=/etc/timeshift/timeshift.json

[ -f "$CONFIG" ] || exit 0
grep -q '"backup_device_uuid" *: *"[^"]' "$CONFIG" 2>/dev/null || exit 0

timeshift --create --comments "Automatic snapshot before system update" --tags D >/dev/null 2>&1

exit 0
