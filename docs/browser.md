# Reyva (the ReyOS browser)

Reyva is ReyOS's private-by-default web browser: a native PySide6 / Qt Quick application on Qt WebEngine (Chromium). It is not a Firefox wrapper. The package and source folder are still called `reyos-browser` (renamed to Reyva on 2026-10-04).

Current version: **0.1.10** (`APP_VERSION` in `main.py`, shown in Settings; bump it with every release).

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
- **Shields:** refreshable ad/tracker domain blocklist with per-site on/off, HTTPS upgrade, tracking-parameter stripping, canvas/WebGL/audio fingerprint noise.
- **Passwords:** saved in the system keyring (Secret Service / KWallet; Windows Credential Manager), save prompt and autofill, CSV import from other browsers.
- **Bookmarks** with folders and HTML import, a bookmarks bar.
- **Downloads** list with progress, notifications, Open, and Show in Folder (file manager's `org.freedesktop.FileManager1`, file selected; Explorer `/select` on Windows). Optional "Ask where to save each file": the dialog comes before `accept()` and the download goes straight into the picked folder when Reyva can write there (`canDownloadInto`; the Flatpak has `--filesystem=/run/media` and `/media` for USB sticks and other drives); only a folder the sandbox can't reach falls back to Downloads-then-move. The portal's `/run/user/<uid>/doc/...` path is mapped to the real one with the document portal's `GetHostPaths`; `safe_file_name()` replaces characters exFAT/FAT/NTFS refuse. Clear button and per-row ✕ remove finished downloads from the list (files stay).
- **Colors follow the ReyOS Look:** `look_palette()` reads the accent from `kdeglobals` (only on ReyOS) and derives the shades with `looks.py`'s HSL targets scaled by the accent's own saturation relative to copper's (so Graphite stays grey); copper everywhere else.
- **Printing:** print preview (printer, pages, copies, layout, paper, color, two-sided) and Save as PDF.
- **Install a site as an app:** its own window and launcher, persistent sign-in for that app (DynamicLauncher portal in the Flatpak).
- Reader Mode, Find in Page, Low Memory Mode (freezes and later discards background tabs; pin a tab to keep it running), video fullscreen, CPU video decoding on Linux (`--disable-accelerated-video-decode`, GPU frames failed on Intel graphics).

## Source

- `reyos-packages/reyos-browser/files/usr/share/reyos/browser/main.py`: backend (`BrowserBackend`), Shields interceptor, passwords, printing, downloads.
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
