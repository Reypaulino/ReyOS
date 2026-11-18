# Reyva (the ReyOS browser)

Reyva is ReyOS's private-by-default web browser: a native PySide6 / Qt Quick application on Qt WebEngine (Chromium). It is not a Firefox wrapper. The package and source folder are still called `reyos-browser` (renamed to Reyva on 2026-10-04).

Current version: **0.1.14** (2026-11-17). `APP_VERSION` in `main.py` is shown in Settings; bump it with every release.

## Where it runs

| Build | How users get it | Updates |
|---|---|---|
| ReyOS | Arch package `reyos-browser`: since 0.1.0-106 only a launcher that installs and runs the Flatpak (`arch-flatpak/usr/bin/reyos-browser`; Arch's Qt 6.12 rollout broke the native build) | Flatpak updates (Discover, Control Center) |
| Any Linux distro | Flatpak `com.reyapps.Reyva` from the signed repo at https://reypaulino.github.io/reyva-flatpak/ (`flatpak/README.md`), or `Reyva.flatpak` from GitHub Releases | Automatic through the Flatpak repo |
| Ubuntu / Debian | `.deb` from GitHub Releases (`debian/build.sh`; builds its Python runtime at install time) | Install the newer `.deb` |
| Windows 10/11 | Per-user installer built by `.github/workflows/reyos-browser-windows.yml` | Run the newer installer |

Only the newest GitHub Release of each build is kept.

## Features

- **Private by default:** off-the-record profile, no persistent history; browsing data is cleared at exit, settings are kept (`settings.json`).
- **Shields:** ad/tracker domain blocklist (StevenBlack hosts + someonewhocares; downloaded on first start and refreshed weekly since 0.1.14, `shieldsAutoUpdate` in Settings › Privacy & Shields, off = only the Update button; the bundled ~150-domain list is only used until the first download) with per-site on/off (reloads the page), per-site blocked count, HTTPS upgrade (not for IP addresses, one-word or local-network names; a site with no working HTTPS can be opened over HTTP for the session), tracking-parameter stripping, canvas/WebGL/audio fingerprint noise.
- **New Tab dashboard (0.1.13):** one search box finds open tabs (switches to them), bookmarks and installed web apps (opens their own window); Enter on plain text searches the web. Ctrl+Shift+A searches open tabs; Settings › Tabs on the side.
- **Welcome tour (0.1.13)** on a new profile only (bookmark/password import, search engine); **Restore tabs after a crash** (0.1.13, opt-in, addresses and titles only, deleted on clean quit).
- **Permissions:** the dialog names the site and what it wants; Privacy & Shields lists this session's answers with Reset (0.1.13; before that, requests were never answered).
- **Passwords:** saved in the system keyring (Secret Service / KWallet; Windows Credential Manager), save prompt and autofill, CSV import from other browsers.
- **Bookmarks** with folders and HTML import, a bookmarks bar.
- **Downloads** list with progress, notifications, Open, and Show in Folder (file manager's `org.freedesktop.FileManager1`, file selected; Explorer `/select` on Windows). Optional "Ask where to save each file": the dialog comes before `accept()` and the download goes straight into the picked folder when Reyva can write there (`canDownloadInto`; the Flatpak has `--filesystem=/run/media` and `/media` for USB sticks and other drives); only a folder the sandbox can't reach falls back to Downloads-then-move. The portal's `/run/user/<uid>/doc/...` path is mapped to the real one with the document portal's `GetHostPaths`; `safe_file_name()` replaces characters exFAT/FAT/NTFS refuse. Clear button and per-row ✕ remove finished downloads from the list (files stay).
- **Colors follow the ReyOS Look:** `look_palette()` reads the accent from `kdeglobals` (only on ReyOS) and derives the shades with `looks.py`'s HSL targets scaled by the accent's own saturation relative to copper's (so Graphite stays grey); copper everywhere else.
- **Printing:** print preview (printer, pages, copies, layout, paper, color, two-sided) and Save as PDF.
- **Install a site as an app:** its own window and launcher, persistent sign-in for that app (DynamicLauncher portal in the Flatpak). When the portal fails without the person cancelling (stock Ubuntu 24.04 refuses every Flatpak launcher's icon; xdg-desktop-portal 1.22.1 locked up on ReyOS), the Flatpak writes `~/.local/share/applications/com.reyapps.Reyva.<app>.desktop` itself (`--filesystem=xdg-data/applications:create`, 0.1.14). Portal calls time out (5–20 s) instead of waiting forever.
- **Video codecs:** the Flatpak (Flathub's QtWebEngine) plays H.264/AAC. The `.deb` and Windows builds use PySide6's pip wheels, which have no proprietary codecs: H.264/AAC sites (e.g. anime/JW Player streams, `JW Player Error 102630`) don't play there; VP9/AV1/Opus do. Use the Flatpak on Ubuntu for those sites.
- Reader Mode, Find in Page, Low Memory Mode (freezes and later discards background tabs; pin a tab to keep it running), video fullscreen, CPU video decoding on Linux (`--disable-accelerated-video-decode`, GPU frames failed on Intel graphics).

## Source

- `reyos-packages/reyos-browser/files/usr/share/reyos/browser/main.py`: backend (`BrowserBackend`), Shields interceptor, passwords, printing, downloads.
- `reyva_core.py`: Qt-free logic (Shields matching, HTTPS-upgrade rule, dashboard search, crash-recovery files, launcher parsing/quoting); tests in `tests/test_reyva_core.py` and `tests/test_reyva_backend.py`.
- `tools/reyva-bench/`: memory/CPU/startup benchmark (`bench.py`, `compare.py`) and GUI checks (`uitest.py`) under Xvfb.
- `qml/Main.qml` (+ `qml/components/`): the UI; `AppWindow.qml` for installed web apps.
- `shields-blocklist.txt`, `fingerprint-protection.js`, `password-autofill.js`, `home.html` (New Tab page).
- Packaging: `PKGBUILD` + `arch-flatpak/` (ReyOS launcher), `debian/`, `windows/`, and `flatpak/` at the repo root.

## Releasing

1. Change the code in a worktree from `origin/main`, bump `APP_VERSION`, add a `<release>` to `flatpak/com.reyapps.Reyva.metainfo.xml`, push to `main`.
2. Pin the Flatpak manifest's `commit:` to that commit (second commit), build the Flatpak, export it signed into the repo, push the repo site, build the bundle, create the GitHub Release (steps in `flatpak/README.md`).
3. `.deb`: `debian/build.sh <version>`, test in a clean `ubuntu:24.04` container, GitHub Release.
4. Windows: run the "Reyva for Windows" workflow with the new four-part version, download the artifact, GitHub Release.
5. Update the download links on the website (`website/index.html`) and delete the previous releases.

History of every change, with what was tested: `docs/fixes.md`. Open problems: `docs/bugs.md`.
