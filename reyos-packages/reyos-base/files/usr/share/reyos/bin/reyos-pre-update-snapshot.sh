#!/bin/bash
# Auto-snapshot before any system upgrade -- closes the rolling-release
# trust gap vs. atomic distros without a full immutable-image rewrite.
# Runs PreTransaction (before, not after) on purpose -- a rollback target
# needs the pre-update state, not the just-broken one.
#
# The work is in reyos-snapshots: on btrfs installs (the default since
# 2026-10-17) it keeps the last two automatic snapshots, frees space first
# when the disk is short, and adds a boot entry per snapshot; with Timeshift
# set up by hand in rsync mode it takes one snapshot as before; with
# Timeshift not set up at all it does nothing.
#
# Must never block a real update over snapshot failure: a pacman
# PreTransaction hook that exits non-zero aborts the whole transaction.
/usr/share/reyos/bin/reyos-snapshots pre-update
exit 0
