# ReyOS — Developer Guide

Custom Arch Linux distro (KDE Plasma 6, Wayland) built via `mkarchiso`, targeting performance/developer/gaming use. Tagline: **"BUILT FOR PERFORMANCE. MADE FOR YOU."**

## Repo layout

```
~/Developer/ReyOS/            (this repo, source of truth)
├── reyos-packages/           PKGBUILDs for every reyos-* package
│   └── <pkgname>/
│       ├── PKGBUILD
│       └── files/            payload, mirrors target filesystem layout
├── reyos-iso/                 archiso profile
│   ├── packages.x86_64        base ISO package list
│   ├── pacman.conf
│   ├── profiledef.sh
│   └── airootfs/              overlay files + customize_airootfs.sh
└── docs/                      this documentation
```

## Package-based architecture

Everything ReyOS-specific ships as a real Arch package (`PKGBUILD` + `makepkg`), installed via a local pacman repo (`[reyos-local]` stanza in `pacman.conf`, `file://` server), not ad-hoc files copied into the ISO overlay. This was a deliberate pivot (2026-08-06) away from an earlier ad-hoc approach.

**Packages so far:**
| Package | Purpose |
|---|---|
| `reyos-base` | `/etc/os-release`, `/etc/hostname` |
| `reyos-wallpapers` | Desktop background |
| `reyos-icons` | Icon theme |
| `reyos-themes` | Global Theme, color scheme, locked panel/taskbar layout, virtual desktops, shortcuts |
| `reyos-welcome` | First-login setup wizard (Kirigami/QML) |
| `reyos-sddm` | Login screen branding |
| `reyos-calamares` | Installer (safe UI-preview mode only — see Calamares section) |

Planned but not yet built: `reyos-plymouth`, `reyos-grub`, `reyos-fonts`, `reyos-control-center`, `reyos-update`, `reyos-store`, `reyos-backup`, `reyos-driver-manager`, and meta-packages (`reyos-desktop`, `reyos-gaming`, `reyos-developer`, `reyos-security`, `reyos-complete`).

## Two VMs

- **`ReyOS`** (build + branded dev VM) — `192.168.122.19`, user `reyrubi` / password set locally (see your own notes, not committed here), passwordless sudo. This is where packages get built and the ISO gets assembled. Also serves as the "live" branded desktop for manually validating changes before a full ISO rebuild.
- **`ReyOS-Test`** — disposable, boots the *actual built ISO* live (not installed). Fully ephemeral — a plain `virsh reboot`/destroy+start gives a genuinely fresh "first login" every time, no need to recreate the domain. Safe to nuke/rebuild anytime.

SSH from this host needs password auth explicitly (no key trust set up), routed through `host-spawn` since the Bash tool itself is sandboxed and can't reach the VM network directly:
```
host-spawn bash -c 'sshpass -p "<dev-vm-password>" ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no reyrubi@192.168.122.19 "<remote command>"'
```
`ReyOS-Test`'s IP changes every boot (DHCP) — get it via `virsh domifaddr ReyOS-Test`, and use `-o UserKnownHostsFile=/dev/null` since its host key changes every boot too (ephemeral).

## Build workflow

1. Edit source locally in this repo.
2. `rsync` changed files to the VM (`~/reyos-packages/...`, `~/reyos-build/reyos-iso/...`).
3. Bump `pkgrel`/`pkgver` in the affected `PKGBUILD`.
4. `cd ~/reyos-packages/<pkg> && makepkg -f --noconfirm`
5. Copy the built `.pkg.tar.zst` into `~/reyos-build/local-repo/` and `repo-add reyos-local.db.tar.gz <pkg>.pkg.tar.zst`.
6. Clean stale build state: `sudo rm -rf ~/reyos-build/work` (a leftover `work/` dir from a prior build can eat several GB and starve the next build of disk space).
7. Build the ISO: `cd ~/reyos-build && setsid nohup bash -c "echo <dev-vm-password> | sudo -S mkarchiso -v -w work -o out reyos-iso" > buildlog 2>&1 < /dev/null &` — `setsid` matters, see gotchas below.
8. Copy the finished ISO to the **host's** `/var/lib/libvirt/images/` (not the VM's own disk) — QEMU/libvirt on this host can only read from trusted locations there, not from a user's home directory.
9. `virsh destroy ReyOS-Test && virsh start ReyOS-Test` to boot the new ISO fresh.
10. SSH in as `liveuser`/`liveuser` (NOPASSWD sudo) and verify.
11. Commit.

Never hand-edit files live on the VM via SSH heredocs except for the build/test commands themselves — this repo is the source of truth.

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
