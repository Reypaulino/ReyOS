# reyos-sddm

ReyOS login-screen branding. This package ships the dedicated ReyOS SDDM
theme under `/usr/share/sddm/themes/reyos/`; it is not a downloaded or stock
internet theme. `/etc/sddm.conf.d/zz-reyos-theme.conf` selects it explicitly.

## Theme assets

- `Main.qml` — ReyOS-owned greeter layout and behavior
- `SDDM-reyos.bmp` — dedicated login background
- `angle-down.png` / `rectangle.png` — local greeter controls
- `theme.conf` — theme metadata and asset selection

## Desktop session labels

Plasma owns the actual Wayland and X11 session files. The
`reyos-brand-sddm-sessions` helper copies their current metadata into SDDM's
higher-priority `/usr/local/share/*sessions` directories and labels them:

- `ReyOS Desktop` — normal Wayland session
- `ReyOS Desktop (Compatibility Mode)` — X11 fallback for hardware/VMs where
  Wayland cannot start

The matching filenames make SDDM deduplicate the upstream entries, so the
menu still contains only two choices. Localized upstream `Name[...]` values
are removed because SDDM otherwise prefers them over the branded base name.
An ALPM hook regenerates both overrides after Plasma session package updates,
preserving upstream command/metadata changes without editing pacman-owned
files.
