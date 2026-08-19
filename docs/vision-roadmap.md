# ReyOS — Product Vision and Roadmap

## State of mind

ReyOS is a calm, dependable KDE Linux distribution: easy enough that a new user can install, use, and update it without becoming a Linux administrator; powerful enough that an experienced user is never boxed in.

It is not a CachyOS clone. Performance matters, especially to give older computers a useful second life, but never at the cost of predictable behavior, clarity, or recovery.

**Promise:** install it, use it, update it, and recover it without fear.

## Product principles

1. **Safe by default.** Curate and test updates, make snapshots/rollback understandable, and avoid unsafe one-click actions.
2. **Simple by default, powerful by choice.** Keep advanced tools available without making ordinary users learn them.
3. **Fast without gimmicks.** Use a lean KDE setup, measured improvements, modest visual effects, and no optimizer daemons.
4. **Respect older hardware.** Provide a low-resource option and make each background service justify itself.
5. **Honest UX.** Explain what a choice does, preserve user control, and never make unsupported reliability promises.
6. **Polished KDE identity.** ReyOS Welcome, Control Center, panels, artwork, and recovery experience should feel like one system.

## OS roadmap

### Foundation — now

- Finish fresh-install validation: Calamares, login, panels, Welcome, Control Center, Wi-Fi, audio, graphics, and shutdown/restart.
- Keep all confirmed bugs, fixes, package versions, and ISO test results documented.
- Measure clean idle RAM/CPU/startup after installation before changing services.
- Retain a lean default install; optional features must not start permanent background work unless users enable them.

### Reliability and recovery — next

- Make system updates a curated, tested ReyOS flow rather than an unexplained raw transaction.
- Offer a pre-update Timeshift snapshot and a simple restore guide in Control Center.
- Establish a release checklist: fresh install, upgrade, rollback, network, audio, suspend, graphics, and low-resource hardware validation.
- Provide clear support diagnostics that users can export without exposing secrets.

### Performance and older hardware

- Add a Welcome choice for **Standard** or **Low-resource** desktop behavior.
- Low-resource mode: restrained animations/effects, no unnecessary autostarts, and clear reversible settings.
- Improve Control Center’s System Info and Startup Apps pages with understandable resource visibility.
- Make changes only from benchmarks and clean-idle baselines; do not clear Linux file cache or ship an optimizer daemon.

### Security — after the reliability baseline

- Keep a safe inbound firewall default with understandable exceptions.
- Make security updates visible and approachable.
- Add a simple installed-package vulnerability check and recovery guidance.
- Research Secure Boot as a fully tested, optional installer feature—not a rushed checkbox.
- State privacy plainly: ReyOS has no telemetry by default; networked features disclose what they connect to.

### Optional capability

- Windows support: optional Wine + Winetricks, with clear compatibility expectations.
- Gaming, creative tools, cloud sync, phone integration, and other large features remain optional Welcome choices.
- Preserve the terminal toolbox for power users, but keep ordinary maintenance available in Control Center.

## Website roadmap

### First release website

- A concise home page with the promise: **“A reliable, beautiful KDE Linux that makes older computers useful again.”**
- Download page with ISO checksum, hardware requirements, installation guidance, and a clear testing/stable channel label.
- Features page: Welcome, Control Center, safe updates, backup/recovery, KDE customization, and low-resource focus.
- Screenshots/video showing a real fresh desktop and real Control Center—not mockups.
- Documentation page: install, update, rollback, Wi-Fi, Windows apps with Wine, and known limitations.
- Transparent project page: release notes, bug tracker, contribution path, and privacy statement.

### Community and trust

- Publish every release checklist and known issue summary.
- Maintain short, human release notes with what changed, what was tested, and how to roll back.
- Invite testers with clear VM and older-hardware test scenarios.
- Avoid performance marketing claims without reproducible measurements.

## Definition of success

A new user can install ReyOS, choose a familiar desktop setup, connect to Wi-Fi, update safely, create a recovery snapshot, and use their computer comfortably—especially an older one—without needing terminal commands or fearing routine updates.

## ReyOS Browser foundation (2026-08-14)

`reyos-browser` is a branded native PySide6/Qt Quick application using the maintained Qt WebEngine (Chromium) renderer; it is not a Firefox wrapper and does not operate a new browser engine. Its current private profile stays in memory, blocks pop-up windows and sensitive permissions by default, and includes ReyOS Shields v1 for a small curated set of network advertising/tracker domains. It does **not** yet claim full EasyList/uBlock compatibility or reliable YouTube-ad blocking. ReyOS does **not** operate a VPN: users connect a provider, workplace, or self-hosted WireGuard profile through the existing Network guide. Future work is visible user control and dependable privacy defaults, not opaque background network services.
