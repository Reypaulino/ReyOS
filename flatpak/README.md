ReyOS Browser Flatpak scaffold

This directory is the starting point for a Flathub submission of ReyOS Browser.

Current status:
- App ID chosen: `com.reyapps.ReyOSBrowser`
- Flathub-specific desktop file added
- Flathub-specific Metainfo file added
- Flatpak manifest aligned to KDE `6.9`
- Qt WebEngine base app wired in: `io.qt.qtwebengine.BaseApp//6.9`
- Wrapper launcher added
- Local build completes with `flatpak-builder`
- Local Flatpak runtime imports verified for `PySide6`, `QtWebEngineQuick`, and `secretstorage`
- **Local OSTree export to `flatpak/repo` now succeeds** (2026-08-24, after freeing host disk space — the free-space failure below is resolved, not just retried)
- **Installed from the local repo and launched successfully** (2026-08-24): `flatpak install --user` from `flatpak/repo`, then `flatpak run com.reyapps.ReyOSBrowser` stayed up and running (not a crash-on-launch), confirmed via `flatpak ps` and a clean kill/teardown

Not done yet:
- Replace the wheel-based Python dependency approach with a Flathub-ready long-term dependency strategy if review requires it
- **Two real sandbox warnings seen on first launch, not yet root-caused**: `Can't get document portal: ... Message recipient disconnected from message bus without replying` (likely affects file open/save dialogs — including the password-manager CSV import — needs the `--filesystem`/portal `finish-args` reviewed), and a `Failed to connect to the bus: ... /run/dbus/system_bus_socket` error (system bus isn't exposed to the sandbox by design; needs confirming this doesn't silently break a feature that assumes it, e.g. some Chromium subsystem)
- Beyond process-alive, no interactive UI check has been done yet — didn't confirm the window actually renders/paints, or that secret storage, downloads, and CSV import work inside the sandbox
- Review and tighten final `finish-args`
- Produce screenshots and final release metadata for Flathub review

Important:
- The current Arch/ReyOS package flow is intentionally left untouched.
- These files are Flathub-specific scaffolding and are not wired into the live `reyos-browser` package yet.
- Local export previously failed here because the host disk was at 99% (4.0G free); freeing space (Trash, pip cache, `.flatpak-builder` cache) resolved it — if this recurs, check `df -h /` first before assuming an OSTree/manifest bug.
