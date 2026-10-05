# Reyva (ReyOS web browser) on Windows

Status (2026-10-05): **released** as `Reyva-Setup-0.1.0.105.exe` (GitHub Release
`reyva-windows-v0.1.0.105`, linked from reyos.reyapps.com). Built and tested by the
"Reyva for Windows" workflow on GitHub's Windows runner: the exe stays up and
renders a URL passed on the command line, the saved-password vault round-trips
through Windows Credential Manager (two accounts on one site, then delete), the
installer installs silently with a Start menu shortcut, the installed copy opens
the New Tab page, and the uninstaller removes the exe and shortcut. Screenshots
are uploaded as run artifacts. Not yet done by a person on a real PC: typing,
autofill on a real login form, notifications, Install as App (checklist below).

## What differs on Windows

| Feature | Linux | Windows |
|---|---|---|
| Saved passwords | KWallet / Secret Service | Windows Credential Manager (`keyring`), plus `%APPDATA%\Reyva\password-index.json` listing usernames per site (no secrets in it) |
| Browser data (bookmarks, shortcuts, settings) | `~/.local/share/reyos-browser` | `%APPDATA%\Reyva` |
| Notifications | `notify-send` | Tray balloon/toast (tray icon shows only while a message is up) |
| Install site as app | `.desktop` file | Start menu shortcut under **Reyva Web Apps**, `.ico` + `index.json` in `%APPDATA%\Reyva\webapps` |
| System password manager | KWalletManager / Seahorse | Credential Manager control panel |
| Taskbar | window class | AppUserModelID `ReyApps.Reyva` (web apps get their own) |

## Build

Easiest: GitHub **Actions -> "Reyva for Windows" -> Run workflow**
(`.github/workflows/reyos-browser-windows.yml`). It builds on a Windows runner,
starts the exe as a smoke test, makes the installer, and attaches
`Reyva-Setup-<version>.exe` to the run as a download.

By hand on Windows (Python 3.12, from `reyos-packages\reyos-browser`):

```
python -m venv windows\.venv
windows\.venv\Scripts\activate
pip install -r windows\requirements.txt
pyinstaller --noconfirm windows\reyos-browser.spec
iscc /DAppVersion=0.1.0.105 windows\reyos-browser.iss
```

`dist\Reyva\` is the app folder (about 800 MB unpacked, a folder build
so Qt WebEngine isn't unpacked to `%TEMP%` on every start);
`dist\Reyva-Setup-<version>.exe` is the installer. The installer is
per-user (no admin prompt), installs to `%LOCALAPPDATA%\Programs\Reyva`,
and its uninstaller removes web app shortcuts but keeps bookmarks/settings.

## Test checklist (first Windows run)

1. Installer runs without an admin prompt; Start menu has Reyva.
2. New Tab page, shortcuts, a few real sites, downloads (Open / Show in Folder).
3. Save a password on a login form, reopen the site: it autofills. It shows up
   in Credential Manager (menu -> Passwords -> System Password Manager).
4. A download finishing shows a Windows notification.
5. Menu -> Install This Site as an App: Start menu -> Reyva Web Apps has it,
   it opens in its own window with its own taskbar icon; Manage Web Apps ->
   Remove deletes the shortcut.
6. Quit and reopen: no tabs or history come back.
7. Uninstall: app and web app shortcuts gone.

## Not done

- **Unsigned**: Windows SmartScreen will warn on first run until code signing
  is set up (separate decision, costs money).
- No auto-update on Windows; a new version means running a new installer.
