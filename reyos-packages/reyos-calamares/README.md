# reyos-calamares

ReyOS's installer configuration and branding for Calamares. The Calamares engine itself is `reyos-calamares-core` (built for ReyOS from CachyOS's Calamares branch, since the CachyOS repositories are no longer used).

This is the real installer: it partitions, copies the live system to disk (`unpackfs`) and installs the bootloader. Test it in a throwaway VM, never on a disk you care about.

## Sequence (`/etc/calamares/settings.conf`)

Pages: `welcome → locale → keyboard → partition → users → summary`, then the install steps, then `finished`.

Install steps, in order: partition, mount, unpackfs, pacman keyring setup, machine-id, fstab, locale/keyboard, LUKS keyfile, mkinitcpio preset fix, Plymouth theme, initramfs, hardware drivers (`reyos-hw-drivers`), removal of the live user, autologin, installer and live-session autostarts (`shellprocess_live_cleanup.conf`), users, firewall, network, display manager, hardware clock, Limine bootloader (+ shim and boot entries), EFI boot entry (`reyos-efi-entry`), systemd services, unmount.

Notable settings:
- Bootloader: **Limine** (`efiBootloaderId: reyos`).
- Default file system: **ext4**.
- Minimum size for ReyOS: **30 GiB** (`welcome.conf` `requiredStorage`; also the smallest partition "Install alongside" creates and "Replace a partition" accepts). Shown as a warning, not a hard stop.

## Module overrides

Calamares' own package ships the module configs under `/etc/calamares/modules/`, so shipping ReyOS's versions at the same paths would be a pacman file conflict. ReyOS keeps them in `/usr/share/reyos/calamares-overrides/` (`welcome`, `users`, `partition`, `unpackfs`, `bootloader`, `grubcfg`, `services-systemd`) and a pacman hook (`reyos-calamares-overrides.hook`, runs when this package or the Calamares engine is installed or upgraded) copies them into place with `reyos-apply-calamares-overrides.sh`. The `shellprocess_*.conf` modules are ReyOS's own and ship directly in `/etc/calamares/modules/`.

## Known gap

`luksopenswaphookcfg` was removed from the sequence (it needs `mkinitcpio-openswap`, which only came from the CachyOS repos): encrypted-swap installs don't get the openswap resume hook.

Changes and test results: `docs/fixes.md`.
