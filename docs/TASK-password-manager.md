# Task: password save/autofill for ReyOS Browser

Status: **not started, no code written**. This is a scoped task handoff — read this whole file before touching anything.

## Why

ReyOS Browser (`reyos-packages/reyos-browser`) is currently private-by-default with an off-the-record `WebEngineProfile` — nothing persists except bookmarks and Shields stats, both explicit user actions. The user wants it to also save and autofill logins, so it can eventually replace a heavier third-party browser as a daily driver. This has been scoped but deliberately not built yet — hand it off cleanly rather than half-build it.

## Ground rules (don't skip)

- Read `AGENTS.md` at the repo root first — it has real, load-bearing rules (never bare `git commit` with no pathspec since this repo can have the user's own unrelated work staged; never push local `master` to the public GitHub remote).
- Read `docs/DEVELOPER.md` for the actual build/test workflow (rsync to the `ReyOS` Dev VM, `makepkg`, `repo-add`, `mkarchiso`) — every `reyos-*` package change goes through this, not a random pip install.
- Bump `pkgrel` in `reyos-packages/reyos-browser/PKGBUILD` for any change to this package.
- Build and actually run it on the Dev VM before calling this done — a login form is easy to get subtly wrong (autofill firing on the wrong field, saving on every keystroke instead of on submit, etc.) and this needs to be seen working, not just compiled.
- Don't touch anything outside `reyos-packages/reyos-browser/` for this task.
- Commit with explicit pathspecs, in logically separate commits if it's cleaner (e.g. one for the backend/vault, one for the QML/UI).

## Current architecture (read the real files, this is a summary not a substitute)

- `reyos-packages/reyos-browser/files/usr/share/reyos/browser/main.py` — `BrowserBackend(QObject)`, Signal/Slot/Property pattern exposed to QML via `engine.rootContext().setContextProperty("browserBackend", backend)`. Bookmarks are the existing precedent for "user explicitly asked to persist this": `~/.local/share/reyos-browser/bookmarks.json`, atomic write (`temp path + os.replace`), `chmod 600`. Follow this exact pattern for anything JSON-based you add (e.g. a "never save for this site" list — see below).
- `reyos-packages/reyos-browser/files/usr/share/reyos/browser/qml/Main.qml` — single `ApplicationWindow`. Note: this file is real but extremely dense (92 lines, most logic packed onto very long single lines) — don't assume it's unfinished because the line count looks small. `WebEngineProfile { id: privateProfile; offTheRecord: true; persistentCookiesPolicy: WebEngineProfile.NoPersistentCookies }` is the whole point of this browser; don't change that globally, passwords are the one deliberate opt-in exception.
- **No `QWebChannel` exists anywhere in this codebase yet.** Page→Python communication today is one-way only (`WebEngineView.runJavaScript(script, callback)`, used by Reader Mode). Passwords need real two-way communication (JS reports a submitted login to Python; Python pushes saved credentials back to JS for autofill) — this is new plumbing.

## Storage: KWallet via the freedesktop Secret Service API, not a custom encrypted file

ReyOS is KDE Plasma; `kwalletd6` already implements `org.freedesktop.secrets` on every real ReyOS session. Use `python-secretstorage` (add to `depends` in the PKGBUILD) rather than inventing a master-password/custom-crypto scheme — the wallet already unlocks with the user's login like everything else on KDE.

Build a `PasswordVault` class:
- `save_credential(origin: str, username: str, password: str)` — one Secret Service item per (origin, username) pair. Attributes: `{"application": "reyos-browser", "origin": origin, "username": username}`. Label: `f"ReyOS Browser: {origin} ({username})"`.
- `get_credentials(origin: str) -> list[dict]` — a site can have more than one saved account.
- `delete_credential(origin: str, username: str)`
- `list_all_origins() -> list[str]`

Expose on `BrowserBackend` using the exact same pattern bookmarks already use — don't invent a different convention:
- `Slot(str, str, str) savePassword(origin, username, password)`
- `Slot(str, result="QVariantList") getPasswordsForOrigin(origin)`
- `Slot(str, str) deletePassword(origin, username)`
- `Property("QVariantList", notify=...) passwordOrigins`

## The QWebChannel bridge (the actual new part)

1. New `PasswordBridge(QObject)`:
   - `Slot(str, str, str) reportFormSubmit(origin, username, password)` — called by the content script when a form with a password field is submitted. This must NOT auto-save — it should trigger the save-prompt UI (below), and only `PasswordVault.save_credential` gets called if the user clicks Save.
   - `Slot(str, result="QVariantList") credentialsFor(origin)` — called by the content script on page load. QWebChannel calls from JS are always async (promise/callback-style in `qwebchannel.js`) — design the content script around that, don't assume a synchronous return.
2. Each `WebEngineView` in `Main.qml`'s tab `Repeater` needs a `webChannel` property set to a `WebChannel { registeredObjects: [passwordBridge] }` (new `QtWebChannel` QML import — not currently used in this file).
3. **Real unresolved gotcha — verify this before assuming it works**: `qwebchannel.js` is the client-side glue script QtWebEngine ships, normally reachable at `qrc:///qtwebchannel/qwebchannel.js` via Qt's resource system. This app currently loads every asset directly off disk via `Qt.resolvedUrl()` with no `.qrc`/resource system set up at all. Confirm the `qrc:` path actually resolves inside a plain PySide6 QQuickWebEngineProfile-based app like this one — if not, locate the real `qwebchannel.js` file inside the PySide6/Qt6 install (it ships as a real file somewhere under the Qt WebChannel module's resources) and vendor a copy into this package's `files/usr/share/reyos/browser/` tree instead of depending on the qrc: path.
4. New content script (new file, e.g. `password-autofill.js`, bundled as a `WebEngineScript` with `injectionPoint: WebEngineScript.DocumentCreation`, `world: WebEngineScript.MainWorld`, added to the profile's `userScripts`):
   - Sets up the QWebChannel, gets the `passwordBridge` object.
   - On `DOMContentLoaded`: calls `credentialsFor(window.location.origin)` — if results exist, finds `input[type=password]` plus the nearest preceding text/email input on the same form and fills them. Does not auto-submit.
   - Listens for `submit` on any form containing `input[type=password]`; extracts origin/username/password; calls `reportFormSubmit(...)`.

## UI — match the existing dark theme exactly, don't introduce a new visual style

Every existing `Dialog`/`Popup` in `Main.qml` uses the same look: `background: Rectangle { color: "#302217"; border.color: "#8E5A2E"; border.width: 1; radius: 12 }`, body text `#FFF3E6`/`#D7C1AA`/`#F4D5A8`. Match it.

- **Save-password prompt**: a small non-modal bar/Popup (not a blocking `Dialog` — shouldn't stop the user from navigating away) with **Save** / **Never for this site** / **Not now**. Only `savePassword` fires on explicit Save.
- **"Never for this site"** needs to persist too, or the prompt just reappears every time — a small JSON blocklist (`~/.local/share/reyos-browser/password-blocklist.json`), same atomic-write + `chmod 600` pattern as bookmarks. This is part of a complete save-prompt, not scope creep — include it.
- **Passwords management dialog**: new entry in the existing `browserMenu` Popup (same place the "Bookmarks" entry lives, `Main.qml` around line 83), opens a new `Dialog` listing saved origins with per-entry Delete. The existing `bookmarksDialog` (`Main.qml` line 81) is a near-identical list+delete UI already built once — mirror its structure closely instead of designing a new pattern.

## Explicitly out of scope — don't build these as a "bonus"

- **Importing existing passwords from Opera GX.** That means reading another browser's own encrypted store with its own separate master key — a materially harder, separate problem from saving new credentials going forward. Not requested.
- Password generator / strength meter.
- Any cross-device sync.

## How to verify this actually works before calling it done

On the `ReyOS` Dev VM (a real logged-in KDE session, where `kwalletd6` auto-unlocks with login — don't test headless):
1. Build + install the updated package (`docs/DEVELOPER.md`'s workflow).
2. Launch `reyos-browser`, go to any real login form, submit it.
3. Confirm the save prompt appears, click Save.
4. Confirm the credential actually landed in KWallet (`kwalletmanager6` GUI, or `secret-tool search application reyos-browser` if available).
5. Close the tab/browser, reopen, revisit the same origin, confirm the fields are actually filled in — not just that the flow runs without erroring.
6. Try "Never for this site" and confirm the prompt doesn't reappear on that origin.

Report back with what was actually tested, not just what was written — this file will be checked against the real result once usage limits reset.
