# Easy Anti-Cheat Linux v2 on ReyOS (saved for later, 2026-11-23)

Owner: "save the anti-cheat for later". Nothing built. Research from 2026-11-23.

## What EAC Linux v2 checks
Epic's new Linux Easy Anti-Cheat (Fortnite's Linux launch) only lets a game start when it can verify how the system was booted:
- Secure Boot with a kernel (and boot manager) signed by a key Epic trusts; measured boot.
- TPM 2.0 (firmware TPM is fine).
- Kernel lockdown `integrity`, only signed modules (`module.sig_enforce=1`), kexec disabled, BPF LSM active.
- IOMMU on (VT-d / AMD-Vi; `intel_iommu=on` on Intel), except handhelds.

Epic reportedly publishes about nine trusted vendor keys (Canonical, Fedora, Debian, openSUSE, Universal Blue, CachyOS…). **Arch is not on it, so ReyOS isn't.** No public process for a distro to get added (Epic's announcement needs a login). Steam Deck: unsupported, Epic talking to Valve. No game was confirmed working as of 2026-11-23.

## How CachyOS does it (November 2026 release, 2026-11-22)
- Opt-in kernel `linux-cachyos-eac` signed with the CachyOS EAC CA, plus `systemd-boot-cachyos-signed`. The user keeps their own Secure Boot keys (sbctl) and only appends the CachyOS CA to `db`.
- `sudo eac-setup` checks TPM/IOMMU/boot manager, enrolls the CA, installs the packages, adds a separate "CachyOS EAC" firmware entry (BootNext); normal entries stay. `eac-status` lists [OK]/[FAIL].
- Limine doesn't verify what it loads, so Limine/rEFInd/GRUB systems boot the EAC kernel through the CachyOS-signed systemd-boot (keep `ENABLE_UKI=no` in `/etc/default/limine`, never `bootctl install`, never sbctl-sign the CachyOS files).
- DKMS modules don't load in the EAC kernel. Prebuilt signed modules instead: `linux-cachyos-eac-nvidia-580xx` (Maxwell/Pascal/Volta: the laptop's 940MX), `-nvidia-open`, `-zfs`, `-r8125`.
- BitLocker/TPM-unlocked disks may ask for their recovery key after the key change.
- Guide: https://wiki.cachyos.org/configuration/easy_anti_cheat/

## Where ReyOS stands
Stock Arch `linux`/`linux-lts` (not signed by a trusted key), Limine, Secure Boot off, NVIDIA 580 via DKMS. The T470p has TPM 2.0 and VT-d.

## Options (recommended: 1, laptop test first, once an EAC v2 game is out)
1. **Opt-in Control Center switch using CachyOS's signed EAC kernel + signed systemd-boot** (Arch-compatible, has the 580xx module), doing what `eac-setup` does. Depends on CachyOS's repo and CA; untested whether EAC accepts it on a non-CachyOS system.
2. **ReyOS's own key trusted by Epic**: contact Epic; ReyOS would build and sign its own kernel + modules for every update. Big ongoing cost, acceptance unknown.
3. Wait for Epic's documentation and the first games.

Changing Secure Boot keys is risky: always opt-in, never default.
