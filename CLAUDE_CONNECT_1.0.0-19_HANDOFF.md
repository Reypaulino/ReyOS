# ReyOS Connect 1.0.0-19 — Claude Code handoff

## Source archive
The prepared source archive is **ReyOS-Connect-1.0.0-19-ReyOS-colors-Claude-handoff.zip**. It was generated in ChatGPT and is **not yet committed or attached to this GitHub branch**. Obtain that archive from the user before applying changes. Do not mistake this handoff note for the actual patch.

## Instructions
1. Start from an up-to-date checkout; compare all patch files with existing source before merging. Preserve newer changes and unrelated features.
2. Check PKGBUILD and version: use 1.0.0-19 only if it is newer than the published package; otherwise increment correctly.
3. Use the official ReyOS copper/orange branding, not the earlier blue logo. Verify SVG, desktop metadata, and Plasma launcher at several icon sizes.
4. Run Python syntax checks, QML/import validation, and supplied Syncthing security tests. Audit subprocess calls, DBus interactions, filesystem paths, and permissions.
5. Validate KDE Connect, Bluetooth, VPN, RDP/VNC/Wayland, and Syncthing; distinguish mocked checks from real hardware testing.
6. Build a clean Arch package with the existing ReyOS pipeline, validate dependencies, file layout, installation and upgrades.
7. Update release notes and audit report with actual commands/results and outstanding bugs.
8. Report package name, version, SHA256 and test results. Ask for approval before publishing, merging to main, or rebuilding the ISO.

## Status
This branch contains handoff instructions only. The ZIP/source changes have not been uploaded or built.