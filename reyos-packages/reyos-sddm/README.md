# reyos-sddm

ReyOS login screen branding — a `theme.conf.user` override for the stock
`breeze` SDDM theme (not a from-scratch theme), plus the ReyOS logo.

`theme.conf.user` is SDDM's own supported override mechanism for a
theme's `theme.conf` — it wins on top of the theme's own settings, so
this never touches files owned by the `sddm` package and survives
`sddm` updates cleanly.

## What it sets
- `background` — ReyOS wallpaper (must match the actual file installed
  by `reyos-wallpapers`, currently a `.jpg` — this tripped up an earlier
  ad-hoc attempt that referenced a `.png` from before the package split)
- `color` — `#0070FF`, ReyOS accent blue
- `logo` — ReyOS logo, shown (stock default hides it)

`/etc/sddm.conf.d/10-reyos-theme.conf` explicitly selects `breeze` as
the active theme rather than relying on it staying the upstream default.
