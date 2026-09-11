#!/bin/bash
set -e
sed -i '/^#\[multilib\]/,/^#Include/ s/^#//' /etc/pacman.conf
