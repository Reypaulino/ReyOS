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
- **`LICENSE` added** (2026-08-31, MPL-2.0, matching the metainfo's `project_license`) — was previously an unbacked placeholder.
- **Manifest source switched from local `dir` to the public git repo** (2026-08-31): `type: git`, `url: https://github.com/Reypaulino/ReyOS.git`, pinned to a commit — Flathub's build servers can now actually resolve it. Rebuilt clean from this source on a second pass.
- **Real bug found and fixed rebuilding from the git source** (2026-08-31): the manifest's install list was missing `fingerprint-protection.js` — `main.py` requires it unconditionally at startup and crashed with `FileNotFoundError` on first real launch. Confirmed fixed: rebuilt, reinstalled, and the app now renders its New Tab page correctly (screenshot-verified on the real host, not just process-alive).
- **First real screenshot added** (2026-08-31): `flatpak/screenshots/new-tab.png`, referenced in the metainfo's new `<screenshots>` block via a `raw.githubusercontent.com` URL (only resolves once this is pushed to the public `main` branch).

Not done yet:
- Replace the wheel-based Python dependency approach with a Flathub-ready long-term dependency strategy if review requires it
- **Two real sandbox warnings seen on first launch, not yet root-caused**: `Can't get document portal: ... Message recipient disconnected from message bus without replying` (likely affects file open/save dialogs — including the password-manager CSV import — needs the `--filesystem`/portal `finish-args` reviewed), and a `Failed to connect to the bus: ... /run/dbus/system_bus_socket` error (system bus isn't exposed to the sandbox by design; needs confirming this doesn't silently break a feature that assumes it, e.g. some Chromium subsystem)
- Beyond the New Tab page, no deeper interactive UI check has been done yet — didn't confirm secret storage, downloads, or CSV import work inside the sandbox
- Review and tighten final `finish-args`
- More screenshots (an actual page loaded, Shields panel) — blocked on having an input-simulation tool on whatever machine does the capture; the real host has none installed (`xdotool`/`wmctrl`/`ydotool`/`wtype` all absent)
- **Domain ownership verification for `com.reyapps.*` against `reyapps.com`** — confirmed via Flathub's docs (2026-08-31) that this needs a token placed at `https://reyapps.com/.well-known/org.flathub.VerifiedApps.txt`. The token itself is only issued once the actual submission PR is opened against Flathub — can't be done ahead of time.
- Actually open the Flathub submission PR once the above is ready

Important:
- The current Arch/ReyOS package flow is intentionally left untouched.
- These files are Flathub-specific scaffolding and are not wired into the live `reyos-browser` package yet.
- Local export previously failed here because the host disk was at 99% (4.0G free); freeing space (Trash, pip cache, `.flatpak-builder` cache) resolved it — if this recurs, check `df -h /` first before assuming an OSTree/manifest bug.
