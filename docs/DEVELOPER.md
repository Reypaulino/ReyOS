# ReyOS — Developer Guide

Custom Arch Linux distro (KDE Plasma 6, Wayland) built via `mkarchiso`, targeting performance/developer/gaming use. Tagline: **"BUILT FOR PERFORMANCE. MADE FOR YOU."**

## Repo layout

```
~/Developer/ReyOS/            (this repo, source of truth; branch main)
├── reyos-packages/           PKGBUILDs for every reyos-* package
│   └── <pkgname>/
│       ├── PKGBUILD
│       └── files/            payload, mirrors target filesystem layout
├── reyos-iso/                archiso profile
│   ├── packages.x86_64       base ISO package list
│   ├── pacman.conf
│   ├── profiledef.sh
│   └── airootfs/             overlay files + customize_airootfs.sh
├── flatpak/                  Reyva Flatpak manifest, metainfo, release steps
├── tools/stable-snapshot/    stable update channel: check, promote, signing key (public)
├── website/                  reyos.reyapps.com (one page + screenshots)
├── wsl/                      ReyOS WSL build
├── .github/workflows/        stable-snapshot check, Reyva for Windows
└── docs/                     this documentation
Branch reyos-pages:           the signed package repo served by GitHub Pages
```

## Package-based architecture

Everything ReyOS-specific ships as a real Arch package (`PKGBUILD` + `makepkg`) in ReyOS's own pacman repo, `[reyos-local]`. Installed systems and the ISO build both get it from GitHub Pages:

```
[reyos-local]
SigLevel = Required
Server = https://reypaulino.github.io/ReyOS/
```

The repo's files (packages, `.sig` files, `reyos-local.db`/`.files`) live on the **`reyos-pages`** branch of this repository (not on `main`). `SigLevel = Required`: every package **and** the database must carry a valid signature from the ReyOS package key (`9A17D49EE3929AC6402337FA66E4085621026272`, public key in `tools/stable-snapshot/reyos-signing-key.asc`), or `pacman -Syu` rejects the whole repo.

**Packages:**
| Package | Purpose |
|---|---|
| `reyos-base` | os-release, hostname, sudoers rules (`/etc/sudoers.d/90-reyos`), pulls in the update channel |
| `reyos-branding`, `reyos-icons`, `reyos-wallpapers`, `reyos-themes`, `reyos-looks`, `reyos-terminal` | Look and feel: icon theme, wallpapers, Global Theme and panel layout, Looks (palette + wallpaper bundles), Konsole/fastfetch |
| `reyos-sddm`, `reyos-plymouth`, `reyos-grub` | Login screen, boot splash, GRUB theme |
| `reyos-welcome` | First-login setup wizard |
| `reyos-control-center-gui` | Control Center (Kirigami/QML) and ReyOS Games; `reyos-admin` privileged helper |
| `reyos-control-center` | ReyOS System Tools (terminal menu) |
| `reyos-update-channel` | Stable (tested Arch snapshot) / rolling channel switch; see "Update channels" |
| `reyos-update-notifier` | Login/30-minute check for newer `reyos-*` packages |
| `reyos-browser` | Launcher for Reyva (installs and runs the `com.reyapps.Reyva` Flatpak) |
| `reyos-reader`, `reyos-connect`, `reyos-distrobox-gui`, `reyos-screenshot`, `reyos-shortcuts-cheatsheet` | Apps: book/comic reader, device dashboard (KDE Connect, VPN, Bluetooth), Distrobox GUI, screenshots, `Meta+/` shortcut list |
| `reyos-preload` | Adaptive preload daemon |
| `reyos-calamares`, `reyos-calamares-core` | Installer configuration and branding; the Calamares engine built for ReyOS |
| `reyos-kde-customization` | Optional extra desktop customization |

Reyva (the browser) is also shipped outside ReyOS: a Flatpak repo (`flatpak/README.md`), an Ubuntu/Debian `.deb` (`reyos-packages/reyos-browser/debian/build.sh`) and a Windows installer (`.github/workflows/reyos-browser-windows.yml`), each published as a GitHub Release (only the newest of each is kept).

## VMs

- **`ReyOS`** (build + branded dev VM) — `192.168.122.19`, user `reyrubi` / password set locally (see your own notes, not committed here), passwordless sudo. This is where packages get built and the ISO gets assembled. Also serves as the "live" branded desktop for manually validating changes before a full ISO rebuild.
- **Test VMs** are made per test and deleted afterwards (the old permanent `ReyOS-Test` domain is gone): for an ISO, a throwaway UEFI VM with Secure Boot off and its disk in `/dev/shm` (see "Build and publish workflow").

SSH from this host needs password auth explicitly (no key trust set up), routed through `host-spawn` since the Bash tool itself is sandboxed and can't reach the VM network directly:
```
host-spawn bash -c 'sshpass -p "<dev-vm-password>" ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no reyrubi@192.168.122.19 "<remote command>"'
```
A test VM's IP changes every boot (DHCP) — get it via `virsh domifaddr <name>`, and use `-o UserKnownHostsFile=/dev/null` since its host key changes too. Add `-o GSSAPIAuthentication=no` if SSH hangs at login.

## Build and publish workflow

1. Change the source in a worktree made from `origin/main` (`git worktree add --detach <dir> origin/main`), never only on a local branch.
2. Bump `pkgrel` (or `pkgver`) in the package's `PKGBUILD`.
3. Copy the package folder to the Dev VM and build there: `makepkg -f --nodeps`. Install it on the Dev VM (`pacman -U`) and test.
4. Sign the built package on the machine that holds the ReyOS package key: `gpg --local-user <key> --detach-sign <pkg>.pkg.tar.zst`.
5. Check out the `reyos-pages` branch (`git worktree add --detach <dir> origin/reyos-pages`) and copy the package + `.sig` into it.
6. Update the database: copy `reyos-local.db.tar.gz`, `reyos-local.files.tar.gz` and the new package(s) to the Dev VM (`repo-add` is Arch-only), run `repo-add reyos-local.db.tar.gz <new-pkg>...` with explicit file names (no glob, no `-s`), and copy **both** database files back (check that both list the new version).
7. Sign both database files (`gpg --detach-sign reyos-local.db.tar.gz`, same for `.files`), and `gpg --verify` every new `.sig` before pushing: one bad database signature breaks the whole repo for every user.
8. Commit and push `reyos-pages` (GitHub Pages serves it within a minute or two), then commit and push the source to `main` with an explicit pathspec.
9. Record the change in `docs/fixes.md`.

`reyos-update-channel` is built and published automatically by `tools/stable-snapshot/promote.sh` (see "Update channels").

**ISO builds** need far more disk than packages (a normal `mkarchiso` run grows the Dev VM's disk by ~13 GB). The method that works on a nearly full host: give the Dev VM 16 GB RAM, build into a tmpfs (`mount -t tmpfs -o size=13G tmpfs /mnt/isobuild`, `mkarchiso -v -w /mnt/isobuild/work -o /mnt/isobuild/out reyos-iso`), then test-install it in a throwaway UEFI VM (Secure Boot off) whose disk is a sparse raw file in `/dev/shm` (at least 34 GB; the installer requires 30 GiB). Never start an ISO build without checking free space on the host first. Release ISOs are split into parts for GitHub Releases (2 GB asset limit).

Never hand-edit files live on the VM via SSH heredocs except for the build/test commands themselves — this repo is the source of truth.

## Update channels (stable snapshot)

Installed systems don't take Arch's live mirrors by default. `reyos-update-channel` (pulled in by `reyos-base`) points `core`/`extra`/`multilib` in `/etc/pacman.conf` at `/etc/pacman.d/reyos-mirrorlist`, which `reyos-channel` writes:

- **stable** (default): one Arch Linux Archive snapshot, `https://archive.archlinux.org/repos/<date>/...`, date from `/usr/share/reyos/stable-snapshot`.
- **rolling**: the servers in `/etc/pacman.d/mirrorlist`.

`reyos-local` (ReyOS's own packages) is always current on both. Users switch in Control Center → Updates → Update channel, or `sudo reyos-channel stable|rolling`. Control Center's Install/Full update run `reyos-channel upgrade`, which on stable also moves Arch packages newer than the snapshot back to it (never `reyos-*` ones), and syncs a second time when the update itself moved the snapshot forward.

The Dev VM runs the stable channel too, so packages are built and tested against the same Arch set users get. `reyos-iso/pacman.conf` includes `/etc/pacman.d/reyos-mirrorlist`, so the ISO is built from that snapshot as well.

**Weekly promotion (automatic):**
1. Every Sunday 06:00 UTC `.github/workflows/stable-snapshot-check.yml` installs all `reyos-*` packages on Saturday's snapshot in an Arch container and runs `tools/stable-snapshot/check-imports.py` (every Python import and QML module the apps use, plus `ldd -r` on PySide6 and Qt's QML/plugin libraries). It opens a GitHub issue: passed or FAILED. Run it for any date with *Actions → Stable snapshot check → Run workflow*.
2. `tools/stable-snapshot/promote.sh` runs daily at 18:00 (systemd user timer, also at the next boot if the PC was off) on the machine with the signing key. When the published stable date is older than the most recent Saturday, it takes the newest passed snapshot, builds `reyos-update-channel` (pkgver = date) in an `archlinux` Docker container, signs it, `repo-add`s it, signs the database, pushes `reyos-pages` and `main`, waits for GitHub Pages and closes the issue. If no newer snapshot passed, it starts the workflow for yesterday's snapshot and waits; a FAILED date is left alone and the next day's is tried. It needs the GitHub login (keyring, so someone logged in) and exits quietly to retry otherwise. Log: `~/.local/state/reyos-promote/promote.log`; desktop notifications on promote/fail.
3. Install or update the timer: `tools/stable-snapshot/install-promote-timer.sh`. By hand: `promote.sh --dry-run` (no workflow, no push), `promote.sh --force --date YYYY/MM/DD` (promote a passed date now).
4. The Dev VM doesn't follow automatically: `sudo reyos-channel upgrade --yes` there after a promotion.

The smoke test itself needs ~4 GB of disk while it runs, so it stays on GitHub. On Arch (ReyOS) promote.sh builds with the system's own `makepkg`/`repo-add` (needs `fakeroot` and `binutils`); elsewhere it uses the ~600 MB `archlinux` Docker image.

Before building a package that needs newer Arch libraries than the current snapshot, promote first; otherwise users on stable can't install it.

## Known gotchas (read before debugging something that looks like this)

- **Plasma 6 autostart doesn't shell-expand `$HOME`.** `systemd-xdg-autostart-generator` runs `.desktop` `Exec=` lines literally — `$HOME/script.sh` fails with status 127. Fix: install scripts to a fixed absolute path (`/usr/share/reyos/bin/...`), point `Exec=` directly at that path, no `sh -c` wrapper.
- **Plasma's own first-boot bootstrap races any script that touches `plasma-org.kde.plasma.desktop-appletsrc`.** No fixed sleep is reliable — Plasma writes this file in an unpredictable multi-pass burst during bootstrap. Real fix: verify-and-retry — apply your change, wait, then check it's *still* there (exact containment count, not just presence of your content, since a stray orphan panel can coexist with your real one). Retry bounded number of times.
- **`KWin reconfigure` does NOT re-read `[Desktops] Number` from `kwinrc` for an already-running session.** Confirmed directly: desktop count stayed at 1 even right after a manual reconfigure call. `VirtualDesktopManager.count` is read-only over D-Bus. The only way to grow a *live* session's desktop count is `VirtualDesktopManager.createDesktop(position, name)`, called once per desktop needed. Still write `Number`/`Rows` to `kwinrc` too, for future logins.
- **A fresh user has no `--user`-scoped flathub remote**, even if flatpak is installed system-wide. `flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo` needed once per new user before any `--user` flatpak install works.
- **`flatpak` itself must be in `packages.x86_64`** — it's easy to add flatpak *usage* (remote-add, install commands) to a first-login script while forgetting the binary itself was never in the base package list. Always sanity-check with `pacman -Q flatpak` on a fresh boot.
- **External (disk-only) VM snapshots and UEFI/pflash firmware:** `virsh snapshot-create-as` fails outright with `internal snapshots of a VM with pflash based firmware are not supported` on this VM's config. Use `--disk-only --atomic` instead. When reverting via `virt-xml --edit --disk path=...`, it only updates `<source>` — it leaves a stale `<backingStore>` element behind, which if it now points at the *same file* as `<source>`, causes `Failed to get "write" lock` (self-referencing backing chain). Fix: `virsh dumpxml`, manually strip the `<backingStore>...</backingStore>` block, `virsh define`.
- **ext4 reserves ~5% of the filesystem for root.** `df` can show `0` available for a regular user while root can still write — don't conclude "still full" from a `df` `0` alone if you're about to retry as root.
- **A killed `mkarchiso` (SIGKILL) leaves bind mounts** (`/proc`, `/sys`, `/dev` under `work/x86_64/airootfs`) that block `rm -rf work` with `Read-only file system` errors. Always let a build exit normally, or explicitly `umount -l` everything under `work/` before cleaning up after a kill.
- **`virsh reboot` (ACPI) can be silently ignored by the guest** — no error, no log entry, VM just keeps running unchanged. If sshd (or anything) is legitimately wedged and a reboot is needed, verify the qemu log actually shows new boot activity; if not, escalate to `virsh reset` (hard reset, guest can't ignore it).
- **Blind `virsh send-key` testing of interactive dialogs is unreliable** (timing races with QEMU key delivery have caused wrong selections more than once). Only trust it for dismissing/cancelling dialogs during rendering checks, never for confirming a real install — prefer real console/virt-viewer interaction or SSH-based state inspection.
