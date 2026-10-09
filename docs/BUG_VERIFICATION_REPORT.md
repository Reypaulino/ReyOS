# ReyOS bug verification report

Date: 2026-10-08 (evening). Verified against `origin/main` at `44e7fc7` and the published packages on `reyos-pages` (Control Center 1.0.0-119, reyos-base 1.1.0-7, reyos-calamares 1.3.6-48, Reyva Flatpak 0.1.1 via reyos-browser 0.1.0-106).

## Summary

| | Count |
|---|---|
| Issues reviewed | 27 |
| Verified Fixed | 5 |
| Partially Verified | 8 |
| Code Fix Found — Not Runtime Tested | 1 |
| Still Reproducible | 3 |
| Unable to Verify | 3 |
| Not re-tested (outside the requested areas) | 7 |

New problems found during verification: 4 (see "New findings").

## Sources and environments

- **Bug history:** `docs/bugs.md` (open) and `docs/fixes.md` (resolved). GitHub Issues hold only 6 automated stable-snapshot issues (#1–#6, all closed by the workflow on 2026-10-08), no bug reports. No pull requests exist. API access worked.
- **Dev VM** (`ReyOS` libvirt domain, Arch, KDE Plasma 6.7 Wayland, software rendering via llvmpipe, no GPU): runtime tests through the real desktop session, screenshots via `virsh screenshot`.
- **Real hardware, read-only:** the user's ReyOS install on the Lenovo laptop (`nvme0n1p3`; Intel HD 630 + GeForce 940MX), inspected from Ubuntu with the partition mounted; nothing changed. Same laptop under Ubuntu for `lspci`.
- **Release artifact:** `reyos-2026.10.01-x86_64.iso` downloaded from the GitHub Release, sha256 matched the published checksum, mounted read-only (udisks loop), files listed/extracted with `unsquashfs`, then deleted.
- **Limitations:** history before 2026-09-11 was squashed into `84ce5b3` on `main`, so older fixes can't be tied to their original commit. No destructive install was run (host disk 8 GB free; a VM install grows the VM image by several GB). No screen access to the real install.

## Results

### Calamares installer and first boot

| Issue | Fix commit | Verification | Result | Remaining action |
|---|---|---|---|---|
| Install aborts with **"Missing variables are: PK"** (shellprocess scripts used bare `$PK`, `$T`, `$u`) | `f8e3530` (reyos-calamares 1.3.6-45) | Source scan of every current `shellprocess*.conf` for bare variables: none left. **Published ISO 2026.10.01 inspected:** contains `reyos-calamares-1.3.6-44` with `$PK` in `shellprocess_hw_drivers.conf` and `$T` in `shellprocess_live_cleanup.conf`, both in the exec sequence of `settings.conf`. ISO assets uploaded 11:20–11:38 CDT; the fix was committed 13:22 CDT. The failure was observed on real hardware on 2026-10-01 (`fixes.md`). Install not re-run today. | **Still Reproducible** (in the published ISO; fixed in source and packages) | Build and publish a new ISO, or mark 2026.10.01 as not installable. Release notes and website don't mention it. |
| Install died in `unpackfs` ("airootfs.sfs does not exist", copytoram on high-RAM machines) | `5ec0b31` | Fix committed 08:30 CDT, ISO's `airootfs.sfs` built 11:08 CDT. A real alongside install on the Lenovo succeeded afterwards (`fixes.md` 2026-10-01). ISO boot entries not inspected today. | Partially Verified | Check `copytoram=n` in the next ISO's boot entries. |
| Live-session leftovers copied into installed systems (tty1 root autologin, sshd + root login, volatile journal, lid switch, pacman-init keyring) | `6a07497` | Real install inspected: no `getty@tty1.service.d`, no sshd/pacman-init/livecd units enabled, no `PermitRootLogin yes`, no `Storage=volatile`, no lid override. | **Verified Fixed** (on the real install) | None |
| "ReyOS Installer is available only from the live session" dialog at every login of an installed system | `5ec0b31` (`--autostart` exits silently outside live) | Current `reyos-launch-installer` exits 0 for `--autostart` when `/proc/cmdline` has no archiso parameters. Real install: launcher has the silent exit; no matching lines in its journal (15,901 lines). Not observed on screen. Note: `/etc/xdg/autostart/reyos-installer.desktop` is reinstalled on installed systems whenever `reyos-calamares` updates (present, dated 2026-10-08 15:46); harmless because of the silent exit. | Partially Verified | User screen check at next login. |
| "Install alongside" blocked: EFI partition "too small (2048 MiB)" | `fixes.md` 2026-09-30 (reyos-calamares 1.3.6-43, pre-squash) | Historical: verified on the rebuilt ISO in a VM and used for the real Lenovo alongside install. Not re-run today. | Partially Verified | None beyond the next ISO test. |

### KDE taskbar icons and application windows

| Issue | Fix commit | Verification | Result | Remaining action |
|---|---|---|---|---|
| Launched apps sometimes get no taskbar entry; icon count fluctuates | None found | Only ever reproduced on VMs with software rendering (llvmpipe); five diagnostic rounds in `bugs.md`, no root cause. No real-hardware observation available. | Unable to Verify | Watch for it on the real laptop (GPU rendering). |
| App launcher (Kickoff) shows no per-app icons | `84ce5b3` (squashed; `fixes.md` 2026-08-26) | Fix present in `fixes.md`; not specifically re-tested. | Code Fix Found — Not Runtime Tested | Include in the user's screen checks. |

### Reyva startup URL loading and address bar

| Issue | Fix commit | Verification | Result | Remaining action |
|---|---|---|---|---|
| Links passed on the command line don't open as tabs | `4df7e29` (packaged in 0.1.0-105) | Dev VM, `reyos-browser <url>` (runs Flatpak 0.1.1), 5 launches: each URL opened as the active tab. | **Verified Fixed** | None |
| **Address bar blank when started with a URL** | None | Dev VM: `https://example.com/a%20b?x=1&y=2` → tab "Example Domain", address bar shows the placeholder. `https://reyos.reyapps.com/#browser-windows` → page loaded and scrolled to the section, address bar blank. `https://kde.org` → address bar correct. **Cause found by reading `qml/Main.qml`:** the address text is only refreshed by `syncCurrentSite()`, called from the view's `onUrlChanged` (if it's the current tab) and from `tabBar.onCurrentIndexChanged`. The first tab's initial URL doesn't emit `urlChanged` after the tab is current; `kde.org` only works because it redirects to `kde.org/`. | **Still Reproducible** (2 of 2 affected URLs) | Proposed fix (not applied): also call `syncCurrentSite()` when the current tab's load finishes (`onLoadingChanged`, `LoadSucceededStatus`). Needs approval. |
| First page at startup loads half-styled (no CSS / images / web font) | None | Dev VM, 3 cold starts with `https://kde.org`: fully styled each time (CSS, banner image, web font). The original trigger (first launch right after a fresh install) wasn't recreated. | Unable to Verify | Keep open; retest on a fresh install. |

### KDE theme switching

| Issue | Fix commit | Verification | Result | Remaining action |
|---|---|---|---|---|
| **Light → Dark: color scheme set, but app content stays light** | None | Dev VM, real `Backend.applyLookAndFeel()` (headless instance; it relaunches Control Center like the UI does), Light → Dark → Light → Dark. After both Dark steps `kdeglobals` says `ColorScheme=ReyOS` (dark, `[Colors:Window] BackgroundNormal=20,16,13`) and the page says "Active: ReyOS Dark", but the relaunched Control Center draws light content. Earlier screenshots the same day (scheme Dark all along) also show light Control Center content. | **Still Reproducible** | Root-cause how Control Center's QML gets its palette (Kirigami/platform theme vs the active scheme). |
| Control Center's own window doesn't pick up a live theme switch | `84ce5b3` (`_relaunch_self`, squashed) | Same run: a new Control Center window opens on the Appearance page after every switch. Dark → Light shows light content correctly; Light → Dark hits the bug above. | Partially Verified | Depends on the bug above. |
| Light theme and Looks undid each other; panels never followed Light | `0764e6f` | Same run: scheme names correct each step (`ReyOSLight`/`breeze` icons, `ReyOS`/`ReyOS` icons), Look kept (copper). **But** the bottom panel stayed light after switching back to Dark, still light 60 s later with plasmashell freshly restarted (see New findings). | Partially Verified | See new finding 1. |

### NVIDIA driver installation

| Issue | Fix commit | Verification | Result | Remaining action |
|---|---|---|---|---|
| Unsupported NVIDIA cards got `nvidia-open-dkms`; Steam pulled NVIDIA packages; Intel labelled AMD on the Drivers page | `7d435ee` | Current `reyos-gpu-detect` run read-only on the Lenovo (Ubuntu, same hardware): Intel `8086:591b` → intel, GeForce 940MX `10de:134d` → `nvidiaOpenSupported: false`, `--packages` empty, `--lib32-vulkan` → `lib32-vulkan-intel`. Real ReyOS install: no NVIDIA packages; vulkan-intel/-nouveau/-radeon and lib32-vulkan-intel installed. Simulated sysfs: RTX 3070 `10de:2484` → `nvidia-open-dkms nvidia-utils`, 940MX-only → nothing. Drivers page, Steam paths and installer all call the same helper. | **Verified Fixed** (reported scenario: Maxwell, hybrid laptop) | A real Turing+ card would confirm the open-driver path (simulated only). |

### System updates and recovery

| Issue | Fix commit | Verification | Result | Remaining action |
|---|---|---|---|---|
| Arch's half-shipped Qt 6.12 broke PySide6 apps (Reyva, Reader PDF) | `bb6234b` (stable update channel) | Real install: `reyos-mirrorlist` → `archive.archlinux.org/repos/2026/10/07`, `stable-snapshot` 2026/10/07, 59 packages moved back to 6.11.2 on 2026-10-08 (pacman log); PySide6 WebEngine/Pdf imports OK (earlier check on the install). Dev VM today: `check-imports.py` against installed packages → Python imports, QML modules, library symbols all OK. | **Verified Fixed** | None |
| Control Center "Install updates" failed without a terminal | `84ce5b3` (squashed; `fixes.md` 2026-09-28) | Real install pacman log 2026-10-08 16:33–16:36: non-interactive `pacman -Sy/-Su --noconfirm` runs from Control Center upgraded 9 ReyOS packages successfully. | **Verified Fixed** | None |
| New icons only appear after a reboot | `b7a0beb` (Refresh desktop) | Dev VM 2026-10-08 through the real UI: dialog showed the button, plasmashell restarted. Not tried on real hardware. | Partially Verified | User screen check. |
| No rollback point before updates (pre-update snapshot) | `84ce5b3` (squashed) | Hook runs before every upgrade on the real install (5 times in the log), but the script exits silently when Timeshift isn't configured, and the install has no `/etc/timeshift/timeshift.json`: no snapshot has ever been taken there. Works as designed, but the website says snapshots are "taken automatically". | Partially Verified | Doc fix (see below); consider prompting to set up Backup Center. |
| Passwordless sudo wildcards allowed root (RB-1) | `1805f99` | Dev VM 2026-10-08: audit attack plus 25 bad inputs refused. Real install not yet checked (in the Codex handoff, section B). | Partially Verified | Codex section B. |
| "ReyOS Recovery" boot entry | `84ce5b3` (squashed) | Never selected live (15 s menu timeout, per earlier notes); the install's `/boot` contents weren't visible from Ubuntu. | Unable to Verify | Test once on the laptop. |

### Not re-tested (open in `bugs.md`, outside the requested areas)

Reader PDF header low contrast; Welcome's `%INSTALLED_DB%` warning spam; Control Center unthemed when launched at the lock screen; Welcome double-click on first launch; SSH to an installed test VM times out (firewall); live boot sometimes has no panels; Folder View settings "About" tab. All left open, unchanged.

## New findings

1. **Bottom panel stays light after Light → Dark** (Dev VM). Panel light right after switching to Dark and still light 60 s later; plasmashell had restarted, `kdeglobals` dark, plasma theme `ReyOS`, transparency 85%. Before the test the panel was dark. Not root-caused; possibly the per-user panel theme or plasmashell's SVG cache. Needs a check on real hardware.
2. **Published ISO 2026.10.01 can't complete an install** (see first row). Highest priority.
3. **Reyva: one line of example.com renders as boxes**: likely no CJK font available in the Flatpak. Cosmetic.
4. **`reyos-calamares-core` doesn't build on the Dev VM**: `cmake: command not found`; its makedepends (boost, cmake, doxygen, extra-cmake-modules, ninja, python-pyaml, python-unidecode) aren't installed there. Environment, not code; the other 24 packages build.

## Regression tests run

| Area | Command / method | Result |
|---|---|---|
| Package builds | All 25 `reyos-packages/*` with `makepkg -f --nodeps --skipinteg` on the Dev VM (temp dir, nothing installed) | 24 built; `reyos-calamares-core` failed for missing build tools |
| Python/shell syntax | `ast.parse` on 32 Python files, `bash -n` on 39 shell scripts from `origin/main` | 0 errors |
| App startup (imports/QML) | `tools/stable-snapshot/check-imports.py /usr/share/reyos` on the Dev VM (CC 119, Reader 40, Welcome 31, Connect 17, Distrobox 6; Qt 6.11.2, PySide6 6.11.2-2) | OK: 71 required imports, 8 QML modules, library symbols |
| CI | `gh run list`: stable-snapshot-check last success 2026-10-08 18:22 (snapshot 2026/10/07, before today's later package releases); Reyva Windows build success 2026-10-05 | Not re-triggered (the workflow opens GitHub issues) |
| Browser | 5 cold starts of Reyva with different URLs (above) | URL→tab OK; address-bar bug reproduced |
| Desktop integration / theme | 4 real `applyLookAndFeel()` switches with Control Center relaunch (above) | Light→Dark content bug reproduced; panel finding |
| Installer configuration | Bare-variable scan of all current shellprocess modules; published ISO inspection | Source clean; ISO has the bug |
| Updates/recovery | Real install pacman log, mirrorlist, hooks, Timeshift config (read-only) | As in the table |

## Outdated documentation

- **`docs/bugs.md`:** the installer-dialog entry is resolved (moved to a Resolved section); the Reyva address-bar, half-styled-page, theme and taskbar entries got 2026-10-08 status notes; the published-ISO installer failure and the panel finding were added. (Edited in the working tree, not committed.)
- **Website (`website/index.html`, live):** (a) Known limitations say the 2026.10.01 installer changes are "checked piece by piece but not yet through a full install"; actually that ISO's installer has a confirmed defect that stops installs. (b) The Control Center card says updates have "a pre-update Timeshift snapshot taken automatically"; only true after Backup Center/Timeshift is set up. (c) "After installing, update first" can't help if the install itself fails. **Not edited**: public wording is the user's call.
- **GitHub Release `reyos-2026.10.01` notes:** say the installer changes "have been checked piece by piece but not yet through a complete install"; don't mention the PK failure. Not edited.
- **README:** points users to the 2026.10.01 ISO without the installer caveat. A one-line caveat was added in the working tree, not committed.

## Recommended next steps

1. **Ship a new ISO** from current packages (installer fix is in 1.3.6-45+), or pull/label 2026.10.01, then update the release notes and website.
2. Approve the one-line Reyva address-bar fix (refresh on load finished), then rebuild the Flatpak and Arch package.
3. Root-cause the Control Center Light → Dark content bug and the panel-stays-light finding, starting on real hardware to rule out the VM's software rendering.
4. On the laptop: screen-check the installer dialog, Kickoff icons, taskbar entries, Refresh desktop and the Recovery boot entry (most are already in the Codex handoff's screen-check table).
5. Re-run the stable-snapshot smoke test when convenient (it covers today's package releases).
6. Fix the website/README wording listed above once the ISO decision is made.
