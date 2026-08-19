#!/bin/bash
# /etc/skel/.bashrc is owned directly by the `bash` package (confirmed via a
# real file conflict during a real ISO build), so shipping our own copy at
# that exact path is a hard pacman conflict -- same pattern as reyos-base's
# lsb-release override. Staged at /etc/reyos/skel.bashrc instead, applied here.
set -e -u
install -Dm644 /etc/reyos/skel.bashrc /etc/skel/.bashrc
