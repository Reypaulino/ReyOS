# ReyOS architecture audit and phased plan (2026-10-16)

Audit of the GitHub repository (`main` at `6c76156` + Control Center 125) and the website (reyos.reyapps.com) against the **ReyOS Core Development Vision**: a lightweight, stable, gaming-ready OS on the existing Arch foundation, with predictable updates, recovery, and validation before anything is called stable.

No source code was changed for this audit. Evidence is given as file paths so each finding can be checked.

## Summary

ReyOS already has the right skeleton: everything ships as signed packages in its own repo, Arch packages come from a dated snapshot (stable channel) that only moves forward after a weekly automated check, there's a pre-update snapshot hook, a recovery boot entry on the ISO, and a broad gaming layer. The gaps are in **depth of validation** (the weekly check only proves the apps' imports load), **partial upgrades** (several ReyOS features sync the package database and then install a subset, which Arch doesn't support), **recovery that only works if the user set it up** (Timeshift is not configured by default, the bootloader has one entry and no fallback), **no testing channel** between "tested snapshot" and "Arch live mirrors", and **no repeatable benchmarks**. The website currently overstates two of these.

## Requirements: implemented, partial, missing

| Requirement | Status | Evidence |
|---|---|---|
| Arch foundation, everything as real packages | **Implemented** | 25 packages in `reyos-packages/`, signed repo `[reyos-local]` on the `reyos-pages` branch (`SigLevel = Required`); source and published versions all match (checked 2026-10-16). |
| Coherent repository snapshots | **Implemented** | `reyos-update-channel`: stable = one Arch Linux Archive date (`/usr/share/reyos/stable-snapshot`); `reyos-channel upgrade` moves packages newer than the snapshot back to it, re-syncs when an update moves the date. |
| Separate stable and **testing** channels | **Partial** | Channels are `stable` and `rolling` (Arch live mirrors). There is no `testing` channel: no place where a candidate snapshot plus new ReyOS packages runs on real machines before stable. New `reyos-*` packages go straight to every user on publish. |
| Avoid unsupported partial upgrades | **Implemented 2026-10-16 (Phase 0)**; was: partial — real risk | Full updates go through `reyos-channel upgrade` (good). But these run `pacman -Sy` then install a subset: Welcome app installs (`reyos-welcome/.../main.py:130-147`), emulator installs (`reyos-install-emulators.sh:42-46`), Steam/gaming installs (`control-center/main.py:1019-1042`), Control Center "Update ReyOS apps" and the new "Updates are ready → Update all" (`PkgWorker._update_reyos_apps`: `pacman -Sy` + `reyos-admin install-reyos`). If the stable date (or, on rolling, Arch itself) moved since the last full update, these install packages built against newer libraries than the installed system. Installing a new `reyos-update-channel` this way also moves the snapshot without upgrading Arch packages. |
| Validate install, boot, updates, dependencies, gaming before stable promotion | **Partial** | `.github/workflows/stable-snapshot-check.yml` + `tools/stable-snapshot/smoke-test.sh`: installs all `reyos-*` packages on the candidate snapshot in a container and checks Python imports, QML modules and `ldd`. Not tested: installing from the ISO, booting, upgrading an existing system from the previous snapshot, the desktop session, gaming. ReyOS package releases themselves have no gate (tested by hand on the Dev VM, then published). |
| Recovery and rollback (bootloader, kernel, packages) | **Partial → improving** (1a done 2026-10-16: backup kernel + fallback entries) | Pre-update Timeshift hook (`reyos-base/.../reyos-pre-update-snapshot.hook`) — **but it does nothing until the user configures Timeshift**, and nothing configures it (no code writes `/etc/timeshift/timeshift.json`). "ReyOS Recovery" boot entry on the ISO (`reyos-iso/efiboot/loader/entries/04-reyos-recovery.conf`) restores a Timeshift snapshot, never exercised through the menu. Installed Limine menu has **one entry** (`shellprocess_limine_entry.conf`): no fallback-initramfs entry (the image is built), no second kernel (only `linux`), no snapshot boot. ext4 default means Timeshift uses rsync (full copies; the laptop's 20 GB root can't hold them). |
| Modern kernels, drivers, KDE, gaming tech | **Implemented** | Arch `linux`, Mesa, Vulkan (Intel/AMD/nouveau), Plasma 6, Flatpak; NVIDIA open driver from Control Center; Steam, GameMode, MangoHud, RetroArch cores, PCSX2/Azahar/Dolphin Flatpaks. Arrive after at most ~1 week (stable) or immediately (rolling). |
| Lightweight default, gaming optional | **Implemented** | ISO list (`reyos-iso/packages.x86_64`, 205 entries) has no Steam/emulators/Wine/office; Welcome and Control Center install them on request. zram, systemd-oomd, reyos-preload. |
| Keep ReyOS Gaming features, per-game profiles, controllers, emulator configs | **Implemented** | `emulation.py`, `games.py`, `game_shrink.py`, `controller_setup.py`: per-game window/resolution, per-console button maps, controller profiles, PCSX2/Azahar configuration, CHD shrinking (Control Center 124). Settings live in `~/.config/reyos/emulation.json`. |
| Measurable performance benchmarks | **Missing** | Only one ad-hoc comparison (NBA Street, Ubuntu vs ReyOS, 2026-10-15) with scripts that live on the laptop (`~/reyos-audit/perf-compare/`), not in the repo. No boot-time, memory, or frame-time baselines per release. |
| Easy install, maintenance, updates, recovery for nontechnical users | **Partial** | Calamares installer (30 GiB minimum, Partition Manager in the live session), Control Center for everything, one-click updates (125), login update notifier. Recovery needs Timeshift set up by hand; no "boot the previous state" path. |
| Preserve user settings through updates | **Mostly implemented** | Packages ship defaults in `/etc/skel` and `/usr`; per-user migrations run at login (`looks.py --reapply-look`). Risk: that login step also rewrites package-owned files under `/usr` to recolor them (`_recolor_look_assets`), which fights pacman's file tracking and makes `pacman -Qkk` report changes. |
| Don't claim stable without evidence | **Partial** | `docs/fixes.md` records what each release was tested on. Website overclaims: "Updates (atomic, …)" — pacman updates aren't atomic; "with a pre-update Timeshift snapshot taken automatically" — only after the user configures Timeshift. |

## Main risks, most serious first

1. **Partial upgrades from feature buttons** (above). Most likely way an ordinary click breaks an install, especially on rolling. Control Center 125's one-click dialog widened it.
2. **No working rollback on a default install.** No snapshots until Timeshift is configured; one boot entry; one kernel.
3. **Promotion checks too little.** A snapshot can pass while the desktop, the installer, booting, or games are broken (the 2026-10-08 Qt 6.12 break was an import failure, which the check does catch; a Mesa or kernel regression would not be caught).
4. **No testing channel.** Every ReyOS package publish reaches every user at once.
5. **Laptop-class disks.** Installs made before the 30 GiB minimum (the laptop: 20 GB, 97 % full) can't hold updates plus rsync snapshots.

## Phased plan

Order: stop the breakage first, then make rollback real, then make validation real, then add the testing channel and benchmarks. Each phase is shippable on its own and keeps every existing feature.

### Phase 0 — Safety fixes (small, first) — **DONE 2026-10-16**

Shipped as control-center-gui 126, welcome 33, update-channel 2026.10.10-2, control-center 26, update-notifier 3 (`fixes.md` 2026-10-16). Left for later: removing the old `pacman -Sy` / per-app sudoers lines from `90-reyos` after the next ISO.


- **No partial upgrades.** One helper, `reyos-admin install-packages` (or `reyos-channel install PKG…`), that runs the channel's full upgrade first and then `pacman -S --needed PKG…` in the same session; Welcome, emulator/Steam installs, "Update ReyOS apps" and "Update all" use it instead of `pacman -Sy` + `-S`. On stable with an unchanged snapshot the upgrade step is a no-op, so normal installs aren't slower. "Update all" becomes: full system update + Flatpaks (it already says system updates live elsewhere; that changes).
- **Website honesty:** drop "atomic"; say snapshots are taken before updates once Backup is set up (until Phase 1 makes it default).
- Dependencies: `reyos-admin`, `reyos-channel`, sudoers rules (`90-reyos`, `reyos-update-channel`) — exact-command rules must cover the new helper.
- Testing criteria: on a Dev VM held at an older snapshot with a newer one published, each install button upgrades first (log shows `-Su` before `-S`), nothing is left at mixed versions (`pacman -Qu` empty afterwards); same on rolling.
- Risks: install buttons take longer when updates are pending (show it in the progress text). Migration: none; behavior change only.

### Phase 1 — Rollback that works by default

**Phase 1a DONE 2026-10-16** (`fixes.md`): `reyos-boot` — LTS backup kernel and a Limine menu kept in step with the installed kernels (normal, LTS, fallback), on existing installs through a normal update. **Phase 1b next:** btrfs + automatic snapshots for new installs (decided: btrfs), snapshot boot entries, exercising the ISO "ReyOS Recovery" entry; needs an ISO build and install tests. Existing ext4 installs don't get automatic snapshots (a near-full disk like the laptop's would fill up); Control Center will offer them with a space check.


- **Snapshots on by default.** Welcome (or first boot) configures Timeshift on the system disk with a small retention (e.g. 3 update snapshots), or, for new installs, switch the default file system to **btrfs** with Snapper/Timeshift-btrfs snapshots (instant, cheap) — design decision below. Keep ext4 installs supported with rsync snapshots and a disk-space check.
- **Boot menu with fallbacks:** Limine entries for the fallback initramfs and for **linux-lts** (install it by default; ~150 MB), written and kept current by a ReyOS pacman hook (`reyos-limine-entries`), replacing the one-off `shellprocess_limine_entry` body. On btrfs: snapshot boot entries (limine-snapper-sync style).
- **Exercise the ISO "ReyOS Recovery" entry** once for real (raise the boot menu timeout for the test).
- Dependencies: Calamares partition config (btrfs subvolume layout `@`, `@home`), Welcome/Backup Center, `reyos-base` hooks.
- Testing criteria: fresh VM install → update → break a package on purpose → boot the previous snapshot or LTS entry → system works; restore via Backup Center; restore via ISO Recovery entry. Disk usage after N updates stays under budget.
- Risks: btrfs default changes installer behavior and needs real-hardware testing; snapshot space on small disks. Migration: existing ext4 installs keep ext4 (no conversion); they get the LTS kernel + fallback entries by package update and a one-time "turn on snapshots" prompt in Control Center.

### Phase 2 — Validation before promotion

- Extend the weekly check from "imports load" to a **VM test run** (on the signing host or a self-hosted runner, since GitHub runners have no KVM): build an ISO from the candidate snapshot + current ReyOS packages, unattended Calamares install (Calamares supports a preseeded config), boot to the desktop, run Control Center/Welcome/Games offscreen checks, run a **previous-snapshot → candidate upgrade** on a saved VM image, reboot, check the session (journal for crashes, plasmashell up), and a short emulator smoke test (RetroArch core loads a public-domain test ROM headless).
- Promotion requires all of it to pass; results (logs, timings) attached to the GitHub issue as the evidence.
- Dependencies: host disk/RAM (current host is nearly full; the in-RAM build method from `docs/DEVELOPER.md` works), QEMU automation already used manually (QMP input).
- Testing criteria: a deliberately broken package (e.g. a QML syntax error in a test build) fails the run; a known-good snapshot passes end to end.
- Risks: run time (~1 h), flaky GUI automation; keep the import check as the fast first gate.

### Phase 3 — Testing channel

- Third channel: `testing` = the **candidate** snapshot + a `reyos-testing` repo (same signing, separate `reyos-pages` path). New ReyOS package builds go to testing first; promotion copies them to `reyos-local` together with the snapshot date after Phase 2 passes and after N days on testing machines (the laptop, the Dev VM).
- `reyos-channel testing`, Control Center channel switch shows it with a warning.
- Testing criteria: a package published to testing doesn't reach a stable machine; switching testing → stable moves packages back cleanly (the existing "newer than snapshot" logic, extended to `reyos-*`).
- Risks: two repos to keep consistent; promotion script must move both atomically (database + packages in one commit).

### Phase 4 — Benchmarks

- Move `perf-compare` (`ps2-perf-test.sh`, `summarize.py`) into `tools/benchmarks/` and add: boot time (`systemd-analyze`), idle RAM after login, app start times (Control Center, Reyva, Games), one 3D/emulation frame-time run (MangoHud CSV), all scripted and run per release on the Dev VM and on the laptop; results appended to `docs/benchmarks.md`.
- Testing criteria: two runs on the same machine agree within a stated tolerance; a regression above threshold blocks promotion (later, part of Phase 2).
- Risks: VM numbers aren't hardware numbers — the laptop stays the reference.

### Phase 5 — Ongoing hygiene

- Stop rewriting package-owned files at login: ship the Look-recolored assets to a user-writable overlay (icon theme in `~/.local/share/icons`, user Aurorae theme) or have the packages read the accent at runtime.
- Keep `docs/bugs.md` triaged (several August entries were never re-checked).

## Decisions needed

1. **Default file system for new installs:** ext4 + Timeshift rsync (no change, slower and larger snapshots) or btrfs + snapshots (instant, boot-to-snapshot possible; bigger installer change).
2. **linux-lts as a default second kernel** (+~150 MB) — recommended.
3. **Where Phase 2 runs:** the Ubuntu host (has the key and KVM, disk is tight) or a self-hosted runner/another machine.
4. **Testing channel audience:** only your machines, or opt-in for beta users.

## Parked work (published 2026-10-16 with Phase 0)

Started on 2026-10-15/16 before this audit and **held** until Phase 0, because two of them add install paths that would inherit the partial-upgrade problem: RustDesk/AnyDesk install option (Control Center Flatpak page + Welcome "Remote Help"), Flatpak updates in the login notifier, "CPU mode: Not available" on machines without frequency control, nav search keywords. They live in an uncommitted worktree; Flatpak-only installs (RustDesk/AnyDesk) don't touch pacman and are safe to ship as they are.
