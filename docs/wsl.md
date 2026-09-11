# ReyOS WSL

A lightweight Arch/ReyOS environment for **Windows Subsystem for Linux 2**.
Purpose: ReyOS development, package building, CLI/dependency/script testing,
and development tooling, from a Windows machine, without a VM.

**ReyOS WSL does not replace the ReyOS ISO.** Keep the two products
separate:

| | ReyOS Desktop | ReyOS WSL |
|---|---|---|
| Ships | full ISO | `.wsl` rootfs artifact |
| Desktop | KDE Plasma, SDDM, Calamares installer | none — terminal + optional WSLg GUI testing |
| Boot | its own kernel, bootloader, initramfs, Plymouth | WSL2's kernel — none of the above apply |
| Hardware | drivers, Bluetooth, sleep/suspend, etc. | passthrough only, mostly untested (see below) |
| Use case | the actual product | fast userspace iteration for building it |

Build tree: [`wsl/`](../wsl/). Directory map + quick build command in
[`wsl/README.md`](../wsl/README.md).

## Architecture

`wsl/build.sh` runs **on the ReyOS Dev VM** (or any Arch/CachyOS host that
already has this repo's `pacman.conf` — cachyos + core/extra repos, keyring,
mirrorlists) and:

1. `pacstrap`s a minimal Arch userspace (`base` + `package-lists/minimal.txt`)
   into a fresh rootfs. `base` deliberately excludes the `linux` kernel
   package — WSL2 supplies its own kernel, ReyOS WSL never ships one.
2. Copies the host's live `pacman.conf`/keyring/mirrorlists into the rootfs
   verbatim, so ReyOS WSL always tracks the same repos and trust as the ISO
   and Dev VM — no separate mirror config to keep in sync.
3. Comments out `[reyos-local]` in the shipped copy (see "Package
   repositories" below — that stanza is a `file://` path local to the build
   machine and would break `pacman -Sy` on every other machine).
4. If a local `reyos-local` repo is present on the build host, bakes a small
   set of WSL-compatible `reyos-*` packages directly into the image via a
   temporary repo stanza, then removes that stanza again. Best-effort — a
   missing local repo does not fail the build.
5. Applies the ReyOS WSL branding/config overlay (`wsl/rootfs/`), the
   `/etc/wsl.conf` template, the first-run script, and the package-list
   files profiles read from at first run.
6. Sets locale/hostname, strips `machine-id` and the pacman package cache,
   and tars the rootfs into `ReyOS-WSL-<version>-x86_64.wsl` + a
   `.sha256` checksum.

No kernel, bootloader, initramfs-as-boot-artifact, Plymouth, SDDM, or
Calamares is ever part of this image — see "Package compatibility
classification" below for the full reasoning per package.

## Supported use cases

- ReyOS development (editing `reyos-*` source, this repo's docs/scripts)
- Package building (`makepkg`, PKGBUILD validation) via `reyos-dev-test`
- CLI testing of `reyos-*` command-line tooling
- Dependency testing (does a package's `depends=()` actually resolve/install
  cleanly on a clean Arch userspace)
- Shell script testing
- General development tooling (git, Python, Node.js, build toolchains)
- Testing selected ReyOS userspace GUI apps through WSLg, where compatible
  (see the classification table)

## Unsupported use cases

Anything that needs a real boot, a real desktop session, or real hardware.
See "What ReyOS WSL must NOT be used to validate" below for the explicit
list — that section is authoritative, this is just the summary.

## Package compatibility classification

| Package | Classification | Why |
|---|---|---|
| `reyos-terminal` | **SUPPORTED** | Konsole/neofetch config + skel files only; baked into the image when available |
| `reyos-control-center` | **SUPPORTED** | terminal quick-launcher wrapping CLI tools (`htop`, `ufw`, etc.) — most sub-actions work, a few (Bluetooth, USB) degrade gracefully to "unavailable" |
| `reyos-screenshot` | **UNSUPPORTED ON WSL** | wraps Spectacle, needs a real compositor/screen to capture |
| `reyos-icons` / `reyos-wallpapers` / `reyos-themes` / `reyos-kde-customization` | **UNSUPPORTED ON WSL** | Plasma desktop theming — nothing to theme without a running Plasma session |
| `reyos-base` | **UNSUPPORTED AS-IS** | depends on `timeshift` + `zram-generator`, both meaningless/undesirable under WSL2 (Windows manages memory; no block device to snapshot). ReyOS WSL ships its own minimal `/etc/os-release`/hostname instead of this package — see "Package differences" |
| `reyos-browser` | **PARTIALLY SUPPORTED** | Qt6 WebEngine app, launches through WSLg if available; **NOT TESTED** this session (no WSLg environment available) |
| `reyos-reader` | **PARTIALLY SUPPORTED** | same as above — Qt6 WebEngine GUI app; **NOT TESTED** |
| `reyos-control-center-gui` | **PARTIALLY SUPPORTED** | most pages (Updates, Performance, Disk) work headless; pages backed by hardware/session state (Bluetooth, VPN interface state, USBGuard) will show "unavailable" rather than fake data — **NOT TESTED under WSLg** |
| `reyos-connect` | **PARTIALLY SUPPORTED** | UI can launch, but real KDE Connect LAN discovery, Bluetooth pairing, and VPN semantics need real network/BT hardware WSL doesn't expose the same way — mark device-facing features **NOT SUPPORTED UNDER WSL** |
| `reyos-distrobox-gui` | **PARTIALLY SUPPORTED** | needs `podman`, which itself needs real container/cgroup support — works if systemd + cgroups v2 are active in the WSL2 kernel, **NOT TESTED** |
| `reyos-preload` | **UNSUPPORTED ON WSL** | learns/prefetches based on real page-cache pressure and process launch patterns on a persistent desktop session — meaningless for a short-lived dev shell, not installed |
| `reyos-calamares` / `reyos-calamares-core` | **UNSUPPORTED** | installer, assumes a target disk to partition/format |
| `reyos-grub` | **UNSUPPORTED** | bootloader theme, no bootloader under WSL |
| `reyos-plymouth` | **UNSUPPORTED** | boot splash, no boot splash under WSL |
| `reyos-sddm` | **UNSUPPORTED** | login manager, no display manager under WSL |

Classification method: static review of each `PKGBUILD`'s `depends=` plus
what the package actually does (`docs/DEVELOPER.md`'s package table was the
starting point). **A package installing cleanly is not the same as it being
supported** — several rows above are marked PARTIALLY SUPPORTED /
NOT TESTED specifically because installing was never attempted with a real
WSLg session in this pass; don't upgrade those to SUPPORTED without an
actual GUI launch and a recorded result.

## Package differences from the ISO

- No `linux`, `linux-headers`, `linux-firmware*`, bootloader (`grub`,
  `limine`, `refind`, `efibootmgr`), `mkinitcpio*`, `plymouth`, `sddm`,
  Calamares, or any KDE Plasma session package.
- No `reyos-base` (see table above) — ReyOS WSL ships its own
  `/etc/os-release` (`wsl/rootfs/etc/os-release`, `VARIANT="WSL"`) and
  `/etc/hostname` directly, set by `build.sh`, without pulling in
  `timeshift`/`zram-generator`.
- No `networkmanager`/`iwd`/Wi-Fi stack — WSL2 networking is host-managed.
- `systemd` is present and enabled (see "Systemd" below) since `base`
  includes it and several dev workflows (fakeroot in `makepkg`, testing a
  `.service` file, `sshd` for remote testing) assume it.

## Package repositories

ReyOS WSL's `pacman.conf` is a copy of the Dev VM's own: `cachyos-v3`,
`cachyos-core-v3`, `cachyos-extra-v3`, `cachyos`, `core`, `extra` are all
live and update normally via `pacman -Syu`.

`[reyos-local]` is present in the file **but commented out**. It points at
`file:///home/reyrubi/reyos-build/local-repo`, which only exists on the
build machine — there is no publicly hosted `reyos-local` repo yet (a known,
already-tracked gap, see `docs/bugs.md` and `docs/DEVELOPER.md`'s "Known
gotchas"). This means:

- Upstream Arch/CachyOS packages update fine via `pacman -Syu`.
- A handful of WSL-compatible `reyos-*` packages (currently just
  `reyos-terminal`) are baked directly into the image at build time,
  best-effort, from whatever's in the build host's local repo at build
  time — they do **not** get live updates inside a running WSL instance.
- Rebuilding other `reyos-*` packages inside WSL itself (for testing) is
  exactly what `reyos-dev-test` + the ReyOS Developer profile are for — see
  below.

## WSL configuration (`/etc/wsl.conf`)

Only non-default settings are set explicitly (see `wsl/wsl.conf` for the
full file with inline reasoning):

- `[boot] systemd=true` — several `reyos-*` dev workflows assume systemd.
- `[user] default=root` at build time, rewritten to the real username by
  first-run setup. **Requires `wsl -t ReyOS` + relaunch to take effect** —
  WSL only re-reads `wsl.conf` on distro (re)start, not live.
- `[interop]`, `[automount]`, `[network]` are left at WSL's own defaults
  (Windows interop, `/mnt/c` automount, host-generated `/etc/hosts` and
  `resolv.conf`) — explicitly listed in the template so the choice is
  documented rather than silently assumed, not because they were changed.

## First launch

First interactive root login (before any real user exists) triggers
`/usr/local/bin/reyos-wsl-init` via `/etc/profile.d/reyos-wsl-firstrun.sh`
(guarded to interactive shells only, and only until
`/var/lib/reyos-wsl/initialized` exists — never re-fires, never fires for
`wsl -e`/non-interactive/script contexts). It:

1. Prints ReyOS WSL branding.
2. Prompts for and creates a real username + password (`useradd -m -G
   wheel`), configures passwordless-free `sudo` via `wheel`.
3. Offers the Minimal / Developer / ReyOS Developer profile choice and
   installs the corresponding `package-lists/*.txt` if not Minimal.
4. Prints the resolved repo list from `pacman-conf --repo-list`.
5. Rewrites `[user] default=` in `/etc/wsl.conf` to the new username and
   marks itself done.

The user then runs `wsl -t ReyOS` + `wsl -d ReyOS` once to pick up the new
default user (a WSL distro-restart requirement, not a ReyOS one).

## Profiles

Implemented as plain package lists (`wsl/package-lists/*.txt`), not new
meta-packages — installed by the first-run wizard, or manually any time:

```
sudo pacman -S --needed $(grep -vE '^#|^$' /usr/share/reyos-wsl/package-lists/developer.txt)
```

- **Minimal** — baked into the shipped artifact. `sudo`, `nano`, `openssh`,
  `curl`, `wget`, `ca-certificates`, `less`, `which`, `man-db`/`man-pages`,
  on top of `base` (which already provides `bash`, `coreutils`, `pacman`,
  `sed`, `grep`, `gawk`, `tar`, `gzip`, `iproute2`, `shadow`, `systemd`,
  `util-linux`).
- **Developer** — adds `git`, `base-devel`, `python`, `python-pip`,
  `nodejs`, `npm`.
- **ReyOS Developer** — adds `pkgconf`, `cmake`, `meson`, `ninja`,
  `shellcheck`, `namcap`, `qt6-base`, `qt6-declarative`, `qt6-tools`.
  Package-specific GUI deps (`kirigami`, `pyside6`, `qt6-webengine`, ...)
  are pulled in per-package by `makepkg -s` itself, not preinstalled here —
  keeps this profile from becoming "install every Qt module ReyOS has ever
  used."

## ReyOS CLI identity

`/etc/profile.d/reyos-banner.sh` prints a two-line banner
(`ReyOS WSL` / `SIMPLE · SAFE · READY TO BUILD`) once per interactive
session, after first-run setup has completed. Guarded on `case $- in *i*)`
so non-interactive shells (scripts, `scp`, CI, VS Code Remote exec) never
see it, and on a `REYOS_WSL_BANNER_SHOWN` env var so it doesn't reprint in
every subshell.

## ReyOS package testing

`reyos-dev-test <pkg-dir> [--install] [--run <binary>]` (installed to
`/usr/local/bin`):

1. Lints the `PKGBUILD` with `namcap` if installed (ReyOS Developer
   profile), warns and continues if not.
2. Runs the real `makepkg -sf --noconfirm` — build errors are shown, never
   swallowed.
3. With `--install`, `pacman -U`s the resulting package.
4. With `--run <binary>`, launches it — refuses with a clear message
   instead of hanging if `$WAYLAND_DISPLAY`/`$DISPLAY` aren't set (no
   WSLg), rather than pretending a GUI launch happened.

## Disposable test environment

```powershell
wsl --import ReyOS $env:LOCALAPPDATA\ReyOS-WSL $env:USERPROFILE\Downloads\ReyOS-WSL-x86_64.wsl   # fresh install (see "Windows installation" below — --install --from-file does NOT work with this artifact)
wsl --list --verbose                                 # confirm it's there
wsl --terminate ReyOS                                # stop without deleting
wsl --unregister ReyOS                               # DELETES the distro's filesystem — confirm before running
```

Re-importing after `--unregister` just means running the install command
again against the same (or a freshly rebuilt) `.wsl` file. There is no
scripted auto-reset command in this repo on purpose — the spec for this
feature explicitly calls for requiring manual confirmation before anything
that destroys a user's WSL filesystem, so `wsl --unregister` stays a
manual, documented step rather than something `wsl/build.sh` or any helper
script runs automatically.

## Windows files

Prefer Linux-side development under `~/Projects` (or similar) inside the
WSL filesystem — cross-filesystem access (`/mnt/c/...`) works
(`[automount]` stays enabled, Windows interop is not disabled) but is
significantly slower for anything doing lots of small file I/O (`git`,
`makepkg`, `node_modules`). Reserve `/mnt/c` access for convenience tasks
(opening a file in a Windows editor, grabbing a downloaded artifact), not
as the working directory for builds.

## Networking

Outbound internet, DNS, and `pacman -Syu` are expected to work via WSL2's
own networking (NAT or mirrored, whichever the installed WSL version
defaults to) — **NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED**, this repo's
build/edit environment has no Windows host to verify against. Do not assume
WSL2 networking matches a physical ReyOS machine's behavior for anything
device-discovery-related:

- KDE Connect (`reyos-connect`) LAN discovery, Bluetooth pairing, and real
  VPN routing semantics are **NOT SUPPORTED UNDER WSL** — WSL2's virtualized
  network adapter does not present the same L2 broadcast/mDNS visibility or
  physical radio access a real machine has.

## Systemd

`[boot] systemd=true` is set. Verification command once on real Windows/WSL2:

```
systemctl is-system-running
```

**NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED.**

Services that should stay disabled under WSL even though `systemd` itself
is on: anything from the "UNSUPPORTED" row of the classification table that
ships a `.service` unit (none currently do — `reyos-preload`, the one
`reyos-*` package with a systemd service, is simply not installed in ReyOS
WSL at all, see the table above).

## Security

- No unsigned repositories — `pacman.conf`'s `SigLevel` and keyring are
  copied verbatim from the trusted Dev VM config, not weakened.
- No Windows firewall/credential/security-policy changes are made by any
  script in `wsl/`.
- No service is exposed publicly by default — `openssh` (client) is
  installed for git/testing use; no `sshd` is enabled.
- Root's password is left locked (pacstrap's own default — no `passwd
  root` is ever run), matching how WSL execs directly into the configured
  user without going through a login/auth prompt.

## Build artifact

`wsl/build.sh` → `ReyOS-WSL-<version>-x86_64.wsl` + `.sha256`, written to
`~/reyos-build/wsl-out/` by default (override with `REYOS_WSL_OUT`). Fully
scripted, no manual assembly steps. Only cleans paths under its own
`$REYOS_WSL_WORK`/`$REYOS_WSL_OUT` (defaults under `~/reyos-build/`) — never
touches anything outside them.

## Windows installation

### Prerequisites (check these first)

Both real bugs found testing this artifact on Windows so far turned out to
be Windows/WSL2 platform setup, not this artifact — worth ruling out
*before* touching `wsl --import`:

- **WSL2's platform features must already be enabled.** `wsl --install
  --no-distribution` (admin PowerShell) enables "Virtual Machine Platform"
  + "Windows Subsystem for Linux" and installs the WSL2 kernel update
  without installing any distro — then **restart the machine**, this does
  not take effect live. A missing platform feature surfaces as `Wsl/
  Service/RegisterDistro/CreateVm/HCS/HCS_E_SERVICE_NOT_AVAILABLE` (real
  case, 2026-09-02, physical Windows 11 machine — fixed by this).
- **Hardware virtualization (Intel VT-x / AMD-V) must be on in
  firmware.** Task Manager → Performance → CPU → "Virtualization" should
  read Enabled. If it's Disabled, that's a BIOS/UEFI setting (often under
  Advanced/CPU) — `wsl --install` cannot flip it for you, and WSL2 will
  not run without it regardless of which Windows features are enabled.
- After enabling/rebooting: `wsl --status` and `wsl --update` to confirm a
  current WSL2 install before trying to import anything.

### Installing this artifact

**Real result, 2026-09-02**: `wsl --install --from-file .\ReyOS-WSL-x86_64.wsl`
was actually tried on a real Windows 11 + WSL2 machine and **failed** —
`error_file_not_found` after the command appeared to finish. Root cause,
best understanding without a Windows dev environment to fully confirm:
`--install --from-file` targets Microsoft's newer packaged `.wsl` format
(an internal manifest + `install.tar.gz`), not a plain rootfs tarball —
which is exactly what `wsl/build.sh` produces, `.wsl` extension or not.
**Don't use `--from-file` with this artifact.** The documented,
always-supported path is the classic tar-based import instead. `wsl
--import` takes three separate arguments — **`DistroName` `InstallLocation`
`SourceFilePath`** — the second one is a new, empty folder WSL creates to
hold the distro's virtual disk, *not* where you downloaded the file. Point
the third argument at wherever the `.wsl` file actually is (e.g.
Downloads):

```powershell
wsl --import ReyOS $env:LOCALAPPDATA\ReyOS-WSL $env:USERPROFILE\Downloads\ReyOS-WSL-x86_64.wsl
wsl -d ReyOS
```

(Confusing this second and third argument — pointing `InstallLocation` at
the download folder instead of a fresh destination — is a real mistake a
tester hit first-try; hence spelling it out here.)

```powershell
wsl --list --verbose      # confirm ReyOS is registered and its state
wsl --unregister ReyOS    # DELETES the distro's filesystem — confirm first
```

**Status: `--install --from-file` confirmed FAIL. `--import` NOT YET
CONFIRMED** — this needs the same real Windows 11 + WSL2 machine to
actually try it before marking it PASS. Don't mark any of the checklist
items below PASS from rootfs inspection alone — they need a real install.
If a future build wants real `--install --from-file` support, that means
producing Microsoft's actual packaged `.wsl` format (manifest +
`install.tar.gz`), which `wsl/build.sh` does not attempt right now.

### Required real-machine tests (all NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED)

**Installation**
- [ ] install WSL if needed
- [x] `wsl --install --from-file` — **FAIL**, `error_file_not_found` (see "Windows installation" above)
- [ ] install ReyOS via `wsl --import` instead
- [ ] launch ReyOS
- [ ] create user via first-run wizard
- [ ] reopen terminal
- [ ] default user works
- [ ] `sudo` works
- [ ] `pacman` works
- [ ] ReyOS/CachyOS repos resolve

**Update**
- [ ] `sudo pacman -Syu`
- [ ] reboot WSL (`wsl -t ReyOS`)
- [ ] reopen, verify no breakage

**Development**
- [ ] clone a test repository
- [ ] compile a small C program
- [ ] run Python
- [ ] run Node.js
- [ ] build a simple PKGBUILD via `reyos-dev-test`

**ReyOS package**
- [ ] build a real `reyos-*` package with `reyos-dev-test`
- [ ] install it
- [ ] test it where compatible

**WSLg**
- [ ] launch at least one compatible Qt ReyOS application, record actual result

## Performance

**NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED.** Once measured, record here:
disk size after install, RAM with shell idle, startup time, process count.
Do not compare directly against the full ReyOS desktop without labeling
which environment each number came from — different kernels, different
memory model (WSL2's dynamic VM memory vs. a real/virtual machine's fixed
allocation).

## What ReyOS WSL must NOT be used to validate

- Calamares installation
- systemd-boot / GRUB / UEFI
- initramfs boot
- Plymouth
- SDDM / full KDE Plasma login
- real GPU driver behavior
- Bluetooth hardware
- sleep/suspend, battery, firmware updates
- recovery boot
- physical disk partitioning
- ISO boot

All of the above still require the ReyOS VM, physical ReyOS hardware, or a
bootable ISO — see `docs/DEVELOPER.md`.

## Recommended development workflow

```
EDIT → BUILD PACKAGE (reyos-dev-test) → INSTALL → TEST USERSPACE → FIX → RETEST
```

in ReyOS WSL for fast iteration, then

```
PACKAGE → ISO → INSTALL → BOOT → DESKTOP → HARDWARE/SYSTEM TESTING
```

in the full ReyOS VM (`docs/DEVELOPER.md`'s build workflow) before treating
a change as done. ReyOS WSL exists specifically to avoid full ISO rebuilds
for simple userspace bugs — it is not a substitute for the VM/ISO cycle
when a change touches boot, the desktop session, or hardware.

## Build verification (ReyOS Dev VM, 2026-09-02)

`wsl/build.sh` was actually run as root on the ReyOS Dev VM (not just
authored) — three real bugs were found and fixed by doing this, not by
static review:

1. **Baked-in `reyos-*` packages silently failed to install.** The bake
   step copied `local-repo`'s files into a differently-named pacman stanza
   (`reyos-wsl-bake`), but the repo's own database file is `reyos-local.db`
   — pacman looked for a `.db` file that didn't exist under that name and
   the sync failed. Fixed by bind-mounting the real `local-repo` path into
   the chroot and reusing the host's own already-correct `[reyos-local]`
   stanza verbatim, only commenting it out *after* the bake step (see
   `build.sh`'s "bake in WSL-compatible reyos-* packages" comment).
2. **Every package download inside the chroot failed** with `could not
   determine cachedir mount point` / `not enough free disk space`, even
   with 19G genuinely free on the host. Root cause: `arch-chroot` warns
   `"$ROOTFS is not a mountpoint"` and, left as a plain directory, pacman's
   disk-space check can't resolve the cache directory's mount boundary at
   all — this isn't cosmetic, it breaks every `pacman -S`/`-U` inside the
   chroot. Fixed by `mount --bind "$ROOTFS" "$ROOTFS"` right after creating
   it, before any `pacstrap`/`arch-chroot` call. **This would have broken
   first-run Developer/ReyOS Developer profile installs and any future
   in-chroot package install, not just the bake step** — worth remembering
   if a similar chroot-based script gets written elsewhere in this repo.
3. **`pacman -Scc --noconfirm` still prompted interactively** (`Do you want
   to remove ALL files from cache? [y/N]`) on this pacman version — dropped
   in favor of a direct `rm -rf` of the cache dir, which was already
   happening right after it anyway.

After all three fixes, a clean re-run produced no prompts and no warnings:
`ReyOS-WSL-2026.09.02-x86_64.wsl`, 261M, `reyos-terminal` correctly baked
in, `sha256sum 64a97010ab320f0c617f85039e7d2d7883133c46f3aeaa5c395e5a490108b2ef`.
The artifact itself was **not** transferred to or tested on Windows — that
step still needs a real Windows 11 + WSL2 machine (none available in this
environment), see the checklist below.

## v1 status

| # | Criterion | Status |
|---|---|---|
| 1 | reproducible `.wsl` artifact can be built | **PASS** — real `sudo ./build.sh` run on the ReyOS Dev VM, three real bugs found and fixed (see "Build verification" above), clean re-run confirmed |
| 2 | installs on Windows 11 WSL2 | **PARTIAL FAIL** — `--install --from-file` real-tested and failed (`error_file_not_found`); `wsl --import` is the documented fix, not yet re-tested |
| 3 | boots to a ReyOS shell | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 4 | non-root user setup works | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 5 | `sudo` works | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 6 | `pacman` works | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 7 | ReyOS/CachyOS repos work | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 8 | systemd works if enabled | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 9 | Developer profile works | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 10 | ReyOS Developer profile builds real `reyos-*` packages | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 11 | a compatible GUI app launches via WSLg | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 12 | unsupported functions documented honestly | done — see classification table + "must NOT validate" above |
| 13 | update/relaunch works | NOT TESTED — WINDOWS WSL2 MACHINE REQUIRED |
| 14 | artifact checksum generated | **PASS** — real sha256 produced, see above |

**Next session**: transfer `ReyOS-WSL-2026.09.02-x86_64.wsl` (or a fresh
rebuild) from the ReyOS Dev VM to an actual Windows 11 + WSL2 machine and
work through the "Required real-machine tests" checklist above, updating
each row from NOT TESTED to PASS/FAIL as it's actually exercised.
