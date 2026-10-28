# ReyOS — Release validation log

What happened when a stable-channel snapshot (or a package release) reached a real machine. One entry per report, newest first. Each entry says who tested, on what, and how far the result goes. A report from one machine is just that: it doesn't validate other hardware, drivers or upgrade paths.

Automated checks (the weekly Stable snapshot check, `tools/stable-snapshot/`) are described in `docs/DEVELOPER.md` → Update channels; this file is for field results.

## 2026-10-27 — Stable snapshot 2026/10/24 on the owner's laptop: update OK (owner report, one machine)

- **Snapshot:** Arch Linux Archive **2026/10/24**, promoted to stable on 2026-10-27 by `promote.sh` after the Stable snapshot check passed (#20): commit `bcb4178`, `reyos-update-channel 2026.10.24-1`.
- **Update date:** 2026-10-27 (the snapshot date and the update date are different things).
- **Machine:** ThinkPad T470p, Intel HD 630 + GeForce 940MX (NVIDIA 580 legacy driver), ReyOS Plasma 6.8 Wayland. The owner's daily-use machine.
- **How:** normal use, Control Center → Updates → Update everything, as a regular user. No shell.
- **Result (owner, GitHub #25):** the update finished with no issues; ReyOS booted and works normally.
- **Version evidence:** not captured yet. Next time on the laptop, without making it a chore: `reyos-channel status` and `pacman -Q linux reyos-update-channel reyos-control-center-gui nvidia-580xx-dkms sunshine` (laptop handoff `~/reyos-handoff/START-HERE.md`, step S1).
- **What this does not cover:** other machines, AMD or NVIDIA-only systems, a fresh install from the ISO, the `rolling` channel, or older snapshots jumping straight to this one.

Still open, not resolved by this report (see `docs/bugs.md`):
- The Stable snapshot check doesn't build `nvidia-580xx-dkms` against the promoted kernel.
- `sunshine` is a fixed upstream binary; after a snapshot change its libraries need an `ldd /usr/bin/sunshine` check (a missing soname would only show up when Remote Play starts).
