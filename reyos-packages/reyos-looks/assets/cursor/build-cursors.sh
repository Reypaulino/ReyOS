#!/bin/bash
# Builds one static XCursor theme per Look (ReyOS-Copper, ReyOS-Crimson, ...)
# from left_ptr.svg + each Look's own colors.colors accent. Run this once on
# a machine with rsvg-convert + xcursorgen (Dev VM: `sudo pacman -S
# xorg-xcursorgen`, rsvg-convert already ships via librsvg, already a
# reyos-control-center-gui dependency) whenever left_ptr.svg's shape or a
# Look's accent changes -- NOT at Look-switch time on the user's machine.
# That's deliberate: applyLook() just does
#   kwriteconfig6 --file kcminputrc --group Mouse --key cursorTheme ReyOS-<Look>
#   plasma-apply-cursortheme ReyOS-<Look>
# (same plasma-apply-* family already used for colorscheme/wallpaper) --
# no new runtime dependency, no new sudo helper, since kcminputrc is a
# per-user file, not root-owned. Only xcursorgen is build-time-only; it
# never ships to end users.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOOKS_ROOT="$HERE/../../files/usr/share/reyos/looks"
ICONS_ROOT="$HERE/../../files/usr/share/icons"
SVG_TEMPLATE="$HERE/left_ptr.svg"

command -v rsvg-convert >/dev/null || { echo "rsvg-convert not found" >&2; exit 1; }
command -v xcursorgen >/dev/null || { echo "xcursorgen not found -- pacman -S xorg-xcursorgen" >&2; exit 1; }

# size xhot yhot, hotspot scaled from the 32x32 source's (4,3) tip.
SIZES=(24 32 48 64)

capitalize() { echo "${1^}"; }

for look_dir in "$LOOKS_ROOT"/*/; do
  look=$(basename "$look_dir")
  colors_file="$look_dir/colors.colors"
  [ -f "$colors_file" ] || continue

  accent_rgb=$(awk -F'=' '/^\[Colors:Button\]/{f=1} f && /^DecorationFocus=/{print $2; exit}' "$colors_file")
  [ -n "$accent_rgb" ] || { echo "skip $look: no DecorationFocus" >&2; continue; }
  IFS=',' read -r r g b <<< "$accent_rgb"
  accent_hex=$(printf '#%02x%02x%02x' "$r" "$g" "$b")

  theme_name="ReyOS-$(capitalize "$look")"
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT

  sed "s/ACCENT_HEX_PLACEHOLDER/$accent_hex/" "$SVG_TEMPLATE" > "$work/left_ptr.svg"

  cfg="$work/left_ptr.in"
  : > "$cfg"
  for size in "${SIZES[@]}"; do
    xhot=$(( (4 * size + 16) / 32 ))
    yhot=$(( (3 * size + 16) / 32 ))
    rsvg-convert -w "$size" -h "$size" "$work/left_ptr.svg" -o "$work/left_ptr_$size.png"
    echo "$size $xhot $yhot left_ptr_$size.png" >> "$cfg"
  done

  out_dir="$ICONS_ROOT/$theme_name/cursors"
  mkdir -p "$out_dir"
  ( cd "$work" && xcursorgen left_ptr.in "$out_dir/left_ptr" )

  for alias in default arrow top_left_arrow left_arrow; do
    ln -sf left_ptr "$out_dir/$alias"
  done

  cat > "$ICONS_ROOT/$theme_name/index.theme" <<EOF
[Icon Theme]
Name=$theme_name
Comment=ReyOS $look pointer, everything else inherited from Breeze
Inherits=breeze_cursors
EOF

  rm -rf "$work"
  trap - EXIT
  echo "built $theme_name ($accent_hex)"
done
