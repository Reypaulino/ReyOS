# ReyOS Browser on Windows

Status (2026-10-04): feature-complete for Windows, **not yet run on a real
Windows machine**. The PyInstaller spec was built and launched on Linux to
check the bundle layout; the Windows-only code paths below need a Windows test.

## What differs on Windows

| Feature | Linux | Windows |
|---|---|---|
| Saved passwords | KWallet / Secret Service | Windows Credential Manager (`keyring`), plus `%APPDATA%\ReyOS Browser\password-index.json` listing usernames per site (no secrets in it) |
| Browser data (bookmarks, shortcuts, settings) | `~/.local/share/reyos-browser` | `%APPDATA%\ReyOS Browser` |
| Notifications | `notify-send` | Tray balloon/toast (tray icon shows only while a message is up) |
| Install site as app | `.desktop` file | Start menu shortcut under **ReyOS Web Apps**, `.ico` + `index.json` in `%APPDATA%\ReyOS Browser\webapps` |
| System password manager | KWalletManager / Seahorse | Credential Manager control panel |
| Taskbar | window class | AppUserModelID `ReyOS.Browser` (web apps get their own) |

## Build

Easiest: GitHub **Actions -> "ReyOS Browser for Windows" -> Run workflow**
(`.github/workflows/reyos-browser-windows.yml`). It builds on a Windows runner,
starts the exe as a smoke test, makes the installer, and attaches
`ReyOSBrowser-Setup-<version>.exe` to the run as a download.

By hand on Windows (Python 3.12, from `reyos-packages\reyos-browser`):

```
python -m venv windows\.venv
windows\.venv\Scripts\activate
pip install -r windows\requirements.txt
pyinstaller --noconfirm windows\reyos-browser.spec
iscc /DAppVersion=0.1.0.102 windows\reyos-browser.iss
```

`dist\ReyOSBrowser\` is the app folder (about 800 MB unpacked, a folder build
so Qt WebEngine isn't unpacked to `%TEMP%` on every start);
`dist\ReyOSBrowser-Setup-<version>.exe` is the installer. The installer is
per-user (no admin prompt), installs to `%LOCALAPPDATA%\Programs\ReyOS Browser`,
and its uninstaller removes web app shortcuts but keeps bookmarks/settings.

## Test checklist (first Windows run)

1. Installer runs without an admin prompt; Start menu has ReyOS Browser.
2. New Tab page, shortcuts, a few real sites, downloads (Open / Show in Folder).
3. Save a password on a login form, reopen the site: it autofills. It shows up
   in Credential Manager (menu -> Passwords -> System Password Manager).
4. A download finishing shows a Windows notification.
5. Menu -> Install This Site as an App: Start menu -> ReyOS Web Apps has it,
   it opens in its own window with its own taskbar icon; Manage Web Apps ->
   Remove deletes the shortcut.
6. Quit and reopen: no tabs or history come back.
7. Uninstall: app and web app shortcuts gone.

## Not done

- **Unsigned**: Windows SmartScreen will warn on first run until code signing
  is set up (separate decision, costs money).
- No auto-update on Windows; a new version means running a new installer.
