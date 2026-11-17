# Reyva audit, improvements and release readiness (2026-11-16)

Work for `docs/handoffs/REYVA_CLAUDE_START_HERE.md` /
`REYVA_CLAUDE_IMPLEMENTATION_TEST_BUGFIX_HANDOFF.md`. Branch
`feature/reyva-lightweight-dashboard-qa`, base `origin/main` `39c1a7b`
(Reyva 0.1.12). **Nothing here is published**: no merge, tag, signed repo,
release or website change.

## 1. What already existed (verified in code at 39c1a7b)

| Area | State before this work |
|---|---|
| Version | `APP_VERSION = "0.1.12"`. `docs/browser.md` said 0.1.10 (stale, fixed). |
| Low Memory Mode | Exists, on by default. Background tab: 2 min inactive → `Frozen` if Chromium's `recommendedState` allows; 8 more min → `Discarded` only if `recommendedState` is `Discarded`. Current tab, pinned ("keep running") tabs and Low Memory off stay active. Chromium's `recommendedState` already keeps audible tabs, capture (camera/mic/screen), PiP and DevTools active and doesn't discard pages with form input. Web-app windows freeze only when minimized, not while audible, with a Keep running pin. ❄/◌ markers on tabs. |
| Memory cleanup | `fingerprint-protection.js` runs V8's full GC 1 s after load and when a tab is hidden (`--expose-gc`, 2026-09-29). |
| New Tab | QML overlay (`NewTabPage.qml`) over a `WebEngineView` that loads the empty `home.html`; search box (web only), up to 12 editable shortcuts, privacy cards. |
| Bookmarks | JSON file, folders, HTML import (`chooseBookmarkImport`/`importBookmarks`/`bookmarkImportFinished`), bookmarks bar. |
| Passwords | Secret Service/KWallet (Credential Manager on Windows), save prompt, autofill, CSV import (`choosePasswordImport`/`importPasswords`). |
| Web apps | Install as app: `.desktop` (native/.deb), DynamicLauncher portal (Flatpak), Start menu (Windows). Own process/window/persistent profile (`AppWindow.qml`, `storageName` = app id). Manage dialog had Remove only. **No way to launch one from Reyva.** |
| Shields | Domain list (149 built-in, ~150k after Update), http→https rewrite, tracking-parameter stripping, fingerprint noise; global and per-site (session) toggle; one global blocked counter. |
| Permissions | One dialog, Allow this session / Block. |
| Crash recovery, first-run welcome, vertical tabs, tab search | Not present. |

## 2. Bugs found

Each was reproduced on the base commit before fixing, then re-tested (§5).

| ID | Severity | Bug | How it was reproduced | Fix |
|---|---|---|---|---|
| B1 | P1 (performance) | With the downloaded Shields list (~150k domains), every request was compared with every domain in Python: **43 ms per request** (microbenchmark), on the request-interceptor thread. | Benchmark `heavy3` (3 pages × 81 requests) vs `heavy3-list150k`: see §4. | `reyva_core.host_blocked`: one set lookup per parent domain (same rule), ~1 µs. |
| B2 | P1 | http:// was rewritten to https:// for **every** host, with no fallback: routers (192.168.x.1), printers, NAS, `localhost` dev servers and http-only sites failed with an SSL error. | Local http server at `http://127.0.0.1:<port>/` → `handshake failed; net_error -107` in the log, page never loads. | `should_upgrade_to_https`: not for IP addresses, one-word names, `localhost`, `.local/.lan/.home.arpa/.internal/...`. For other sites, when an upgraded load fails, a bar offers **Open over HTTP** for that site, this session only. |
| B3 | P1 | Permission requests were **never answered**: QML called `permission.reject()`, which doesn't exist on Qt 6.8+'s `WebEnginePermission` (it's `deny()`). Block threw a TypeError; Esc/close left the site waiting forever. The dialog also showed the *current* tab's host, not the site that asked, and didn't say what was asked; a second request replaced the first unanswered. | Background tab calls `navigator.geolocation.getCurrentPosition`, dialog closed with Esc: base → the page's promise never settles; uitest `permissions`. | `deny()`/`grant()`; dialog names the requesting origin and the permission; requests queue. |
| B4 | P2 | Installed web apps on the `.deb`/native build: a title containing `"`, `$`, `` ` `` or `\` produced a launcher GIO refuses ("Desktop file didn't specify Exec field"); an address with `%20` opened the wrong page (`a%20b` → `a0b`). | `desktop-file-validate` ("invalid field code %2") and launching test entries through GIO (`tests/test_reyva_core.py::test_launchers_get_the_real_address`). | `quote_desktop_exec_arg` applies both escaping levels of the Desktop Entry spec and `%%`. Existing launchers keep working (parser accepts the old form). |
| B5 | P3 | Settings › "What's new" / "Report a problem" opened their tab in the background, so the click seemed to do nothing. | Code + UI. | `openInNewTab(url, select)`. |
| B6 | P3 (efficiency) | `installedWebApps` re-scanned `~/.local/share/applications` (Flatpak: one D-Bus `GetDesktopEntry` per app) on every QML read; the Web Apps dialog binds it 4 times. | Code. | Cached; refreshed on install/remove and when the dialog opens. |
| B8 | P3 | Bookmark import dropped a link whose `</A>` was missing (hand-edited or damaged files). | `tests/test_reyva_backend.py::test_malformed_and_oversized_bookmark_files` failed on the base parser. | Pending link is kept when the next entry starts / at end of file. |
| B9 | P3 | The browser menu was taller than a 760 px window: Quit was cut off, no sign it scrolls. Owner report. | Screenshot. | Shorter rows in short windows, scroll bar below that. |
| B10 | P3 | Reload icon off-center, bluish, thinner than the other icons. Owner report. | Rendered SVG. | Redrawn. |
| B11 | P3 | Install as App dialog used Qt's default title bar/field/buttons; Manage Web Apps cut each app's address; Privacy & Shields called the New Tab page "not secure". Owner reports / found while checking. | Screenshots. | Restyled; site name only; New Tab text. |
| B7 | P3 | Web-app icons in the Web Apps list were built as `"file://" + path` (breaks on `#`/`?` in a path). | Code. | `QUrl.fromLocalFile` in Python (`iconUrl`). |

Not reproduced, left open: `bugs-old.md` "first page opened at startup can load half-styled" (not seen in any run of this work).


## 3. What changed (scope of the seven improvements)

| # | Improvement | Done | Reused | Deferred / not done |
|---|---|---|---|---|
| A | RAM / leaks | B1 (filter list), B6 (web-app list cache). Welcome and the side tab list are created only while shown (`Loader`). No polling, timers, indexers or extra web views added. | Existing GC hook, Low Memory Mode. | No leak was found with evidence (tab churn, §4); nothing was "fixed" without one. |
| B | Startup / idle CPU | Nothing new runs at start-up except reading `settings.json` once more and, with recovery on, a folder listing. Idle CPU measured 0–0.03 s per 30 s before and after. | | |
| C | Tab sleeping | Sleeping/unloaded state shown in the dashboard, tab search and side tabs; switching from them is the only thing that wakes a tab. | Freeze/discard timers, `recommendedState`, pin, all unchanged (2 min / +8 min). | No timing change: nothing measured justified one. |
| D | Crash recovery | Opt-in, off by default (`reyva_core.RecoveryStore`): per-process `recovery-<pid>.json` (0600) + a lock held while running; only http(s) addresses and titles; written 1.5 s after a tab change, atomically (fsync + rename); deleted on clean quit, after Restore/Discard, and when switched off. Restore/Discard bar only after a real unclean exit (a lock nobody holds). | Settings file. | Not encrypted: the key would have to sit next to it or in the wallet (absent on fresh KDE installs); exposure is limited to addresses+titles, 0600, deleted on clean exit. Documented in the setting's text. |
| E | Welcome | 5 skippable steps (`WelcomeWizard.qml`): privacy, bookmark HTML import with per-browser export steps, optional password CSV with an unencrypted-file warning and the wallet note, search engine, tips. `onboardingCompleted` in `settings.json`; never shown when the profile already has any file (upgrades), nor when started with a link. Settings › Welcome tour replays it. | `chooseBookmarkImport`, `choosePasswordImport`, `setSearchEngine`, wallet note. | |
| F | Vertical tabs + tab search | Settings › Tabs on the side (default top). Side list uses the same `tabs` model and `tabBar.currentIndex`; no extra views. Ctrl+Shift+A / search button: open-tab search. | Tab model, close/pin/select functions. | Tab groups: not built (handoff: optional). |
| G | Shields / permissions | Per-site blocked count, filter list size/date/Update/error in Privacy & Shields, plain explanation of what it can't do, site toggle reloads the page, per-site permission list with Reset (`listPermissionsForOrigin`, in-memory for the private profile). B2, B3. | Interceptor, filter list updater. | Persistent per-site permission overrides: not added (private profile; nothing persisted). |
| — | Smart Dashboard | `NewTabPage.qml` + `reyva_core.dashboard_results`: Open tabs / Web apps / Bookmarks / Search the web, All / per-kind chips, keyboard (Up/Down/Enter/Esc), switching to the exact existing tab (an empty New Tab you came from is closed), bookmarks via `openBookmarkUrl`, web apps via new `launchInstalledWebApp(app_id)`. | | No thumbnails/remote icons (by design). |

`launchInstalledWebApp` only accepts an id from the installed list (`reyos-webapp-[a-z0-9-]+`), and takes only the address/title/icon from the launcher (never its command); it starts Reyva itself (`python main.py --app-url=…`, or the .exe) without a shell. Web-app windows keep their own persistent profile (`storageName` = app id); the main window stays off-the-record.

Added after owner review the same evening (all screenshot-checked): toolbar **Web Apps** grid (one click opens an app), **Install as App** button at the end of the address bar, side tabs **fold to icons** (remembered), dimmed backdrop behind dialogs, crash recovery in its own Settings section, and the welcome became a **guided tour** (each step lights up the part of the window it explains; imports and search engine inside the steps).

## 4. Performance (before / after)

`tools/reyva-bench/bench.py`, 3 runs each, same machine and session, Xvfb 1600×1000, `.deb` venv (PySide6/Qt 6.11.2), local HTTPS test pages, throwaway profile. Raw: `tools/reyva-bench/results/2026-11-16-*.json`. PSS = whole process tree.

Before: baseline origin/main 39c1a7b (Reyva 0.1.12) · After: candidate feature/reyva-lightweight-dashboard-qa (0.1.13)  
Machine: {'kernel': '7.0.0-43-generic', 'cpu': 'Intel(R) Core(TM) i7-7820HQ CPU @ 2.90GHz', 'ram_gb': 31.1, 'distro': 'Ubuntu 24.04.5 LTS', 'pyside': '6.11.2 6.11.2', 'governor': 'performance'}  

| Scenario | Metric | Before | After | Change |
|---|---|---|---|---|
| blank | Ready (s) | 1.05 (1.02–1.08) | 2.05 (1.91–2.08) | +95% |
| blank | PSS (MB) | 397.5 (396.3–398.3) | 407.2 (406.8–407.3) | +2% |
| blank | RSS (MB) | 594.8 (593.6–595.4) | 604.7 (604.5–604.7) | +2% |
| blank | Web processes | 3 | 3 | +0% |
| blank | Idle CPU (s/30 s) | 0.00 | 0.00 |  |
| tabs1 | Ready (s) | 1.14 (1.10–1.16) | 1.10 | -4% |
| tabs1 | PSS (MB) | 406.8 (405.3–406.9) | 410.7 (410.6–411.6) | +1% |
| tabs1 | RSS (MB) | 610.3 (608.7–610.5) | 613.9 (613.8–614.6) | +1% |
| tabs1 | Web processes | 3 | 3 | +0% |
| tabs1 | Idle CPU (s/30 s) | 0.00 | 0.00 |  |
| tabs5 | Ready (s) | 1.23 (1.22–1.25) | 1.24 (1.20–1.27) | +1% |
| tabs5 | PSS (MB) | 522.2 (521.8–523.2) | 527.6 (527.5–528.1) | +1% |
| tabs5 | RSS (MB) | 1065.9 (1065.8–1067.7) | 1074.6 (1072.9–1075.1) | +1% |
| tabs5 | Web processes | 7 | 7 | +0% |
| tabs5 | Idle CPU (s/30 s) | 0.01 (0.00–0.01) | 0.01 (0.00–0.01) | +0% |
| tabs10 | Ready (s) | 1.48 (1.39–1.54) | 1.40 (1.25–1.46) | -5% |
| tabs10 | PSS (MB) | 637.2 (634.3–637.3) | 575.1 (574.1–575.9) | -10% |
| tabs10 | RSS (MB) | 1606.6 (1605.0–1607.7) | 1615.4 (1613.2–1615.8) | +1% |
| tabs10 | Web processes | 12 | 12 | +0% |
| tabs10 | Idle CPU (s/30 s) | 0.02 (0.01–0.03) | 0.01 (0.01–0.02) | -50% |
| tabs20 | Ready (s) | 1.81 (1.73–2.10) | 1.79 (1.75–1.83) | -1% |
| tabs20 | PSS (MB) | 897.2 (896.4–898.9) | 847.2 (843.8–847.8) | -6% |
| tabs20 | RSS (MB) | 2722.4 (2720.7–2724.5) | 2746.5 (2743.7–2748.5) | +1% |
| tabs20 | Web processes | 22 | 22 | +0% |
| tabs20 | Idle CPU (s/30 s) | 0.01 (0.01–0.02) | 0.02 (0.02–0.03) | +100% |
| heavy3 | Ready (s) | 1.83 (1.62–2.15) | 1.71 (1.65–1.71) | -7% |
| heavy3 | PSS (MB) | 462.6 (462.4–462.9) | 392.3 (391.5–393.0) | -15% |
| heavy3 | RSS (MB) | 835.7 (835.5–836.4) | 841.7 (840.9–842.5) | +1% |
| heavy3 | Web processes | 5 | 5 | +0% |
| heavy3 | Idle CPU (s/30 s) | 0.00 | 0.00 |  |
| heavy3-list150k | Ready (s) | 18.17 (14.04–20.13) | 1.80 (1.77–2.02) | -90% |
| heavy3-list150k | PSS (MB) | 479.0 (477.9–480.2) | 402.2 (377.9–402.4) | -16% |
| heavy3-list150k | RSS (MB) | 852.9 (851.2–854.1) | 861.8 (858.7–861.8) | +1% |
| heavy3-list150k | Web processes | 5 | 5 | +0% |
| heavy3-list150k | Idle CPU (s/30 s) | 0.00 | 0.00 |  |
| churn | Ready (s) | 2.08 (1.98–4.87) | 1.37 (1.25–1.48) | -34% |
| churn | PSS growth (MB) | 33.4 (30.4–39.2) | 27.6 (13.0–61.0) | -17% |

Reading it:
- **Big filter list (B1): page load 18.2 s → 1.8 s.**
- Memory: PSS flat (±2%) for 0–5 tabs, lower for 10/20 tabs and the heavy pages (−6…−16%); RSS +1% everywhere (the new QML). No extra web processes. Idle CPU ≤ 0.03 s per 30 s before and after.
- Tab churn (30 open/close cycles): growth 33 → 28 MB median, within noise; no leak found.
- `blank` "Ready" +95% in that run was the first welcome version on a fresh profile. Re-measured with the final code, 5 alternating starts each: fresh profile (tour shown once) 1.29 → 1.47 s; normal start (tour already seen) 1.37 → 1.31 s.

## 5. Tests run

| Test | Environment | Result |
|---|---|---|
| `tests/test_reyva_core.py` (26) | sandbox Python 3.14 and host Python 3.12 + GIO | PASS (GIO launcher test runs on the host only) |
| `tests/test_reyva_backend.py` (13) | `.deb` venv, PySide6 6.11.2 | PASS |
| `tools/reyva-bench/uitest.py` (21 checks: tour, upgrade skip, start-with-link, dashboard tab/bookmark/web app/web search, tab search, side tabs, local http, HTTPS fallback + Open over HTTP, permission deny, crash save/Restore/Discard/off, downloads, clean quit) | Ubuntu 24.04 host, Xvfb, real app | 21 PASS. Base code: local http FAIL, permission FAIL (`Main.qml:342: Cannot assign [undefined] to QString`, request never answered) |
| Screenshots reviewed | tour steps, dashboard, tab search, side tabs folded/unfolded, Settings, Shields + permissions, HTTPS bar, recovery bar, Install as App, Web Apps grid and Manage with the owner's 5 real apps | OK |
| Owner on the Ubuntu desktop | candidate run from source | menu, reload icon, Install as App, Settings, side tabs, Manage reported and fixed |
| `.deb` 0.1.0-129ubuntu1 clean `ubuntu:24.04` container | see fixes.md | see fixes.md |
| Flatpak, Windows | see fixes.md 2026-11-16 (0.1.13) | |
| ReyOS (Arch launcher → Flatpak) on real hardware | — | NOT TESTED (laptop handoff) |
| Real camera/microphone grant, geolocation fix (geoclue disabled on the host) | — | NOT TESTED |

## 6. Known issues left

- P3: tab groups not built (optional in the handoff).
- P3: crash-recovery file isn't encrypted (by design, see §3 D).
- P3: in the address-bar step of the tour the unchecked search-engine radio is hard to see (Fusion's radio on a dark card).
- `bugs-old.md` "first page half-styled": not reproduced.

## 7. Verdict

GO, approved and published by the owner on 2026-11-16 ("publish … update everywhere"). Release details: `docs/fixes.md` 2026-11-16 (Reyva 0.1.13).
