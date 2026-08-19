# reyos-calamares

ReyOS's own `/etc/calamares/settings.conf`, overriding whatever the
`cachyos-calamares` package ships by default — this is the standard,
expected way to customize Calamares (each distro provides its own
settings.conf; there's no `.conf.user`-style override mechanism for it
like SDDM's theme.conf, distros just replace the file directly).

## Current state: SAFE PREVIEW ONLY

`exec: []` — the sequence has no disk-modifying modules anywhere in it.
Clicking all the way through the UI does nothing to the disk; it just
reaches the "finished" page. This is intentional and load-bearing:
**do not add real exec modules (partition, mount, unpackfs, bootloader,
etc.) without deliberately reviewing and testing that change** — this
file existing safely is what makes it okay to test-launch Calamares on
a live desktop VM at all.

## Why `cachyos-calamares` and not `cachyos-calamares-qt6-next-grub`

The `-qt6-next-grub` variant (and most of the other `-qt6-*` suffixed
variants) has version-pinned native dependencies
(`libyaml-cpp.so.0.8`, `libpython3.13.so.1.0`,
`libboost_python313.so.1.89.0`) that have drifted out of sync with the
current rolling-release package set. The plain `cachyos-calamares`
depends on generic `python`/`yaml-cpp` package names instead of pinned
SONAMEs and has no boost-python dependency at all — it launches cleanly
with the current package snapshot. If this stops working after a
future system update, check `ldd $(which calamares)` for missing
libraries before assuming Calamares itself is broken again.

## Sequence

`welcome → keyboard → users → finished` — no `locale` (timezone) step.
ReyOS Welcome already has its own timezone setup that runs right after
first login, so asking for it twice would be redundant. Language
selection stays on Calamares' own Welcome page (a separate control from
timezone, not affected by dropping `locale`).
