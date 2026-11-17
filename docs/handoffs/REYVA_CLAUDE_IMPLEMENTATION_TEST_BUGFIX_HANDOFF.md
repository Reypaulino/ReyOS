# Reyva Browser — Claude Code Implementation, Bug Audit, Test & Build Handoff

**Prepared:** 2026-11-16  
**Repository:** https://github.com/Reypaulino/ReyOS  
**Target:** Reyva desktop source shared by ReyOS Flatpak and Ubuntu/Debian .deb, plus updates to the download website.  
**Owner's release rule:** **Do not publish, upload binaries, tag, push to release branches, or update public website downloads without explicit owner approval.** Build locally and report complete test results first.

## 0. Instructions to Claude — start here

You are working on an EXISTING, functional, privacy-focused browser, not building a new browser. First `git fetch`, inspect latest `origin/main`, record HEAD SHA and actual app version, and review `docs/browser.md`, `docs/bugs.md`, `docs/bugs-old.md`, `docs/fixes.md`, `flatpak/README.md`, and relevant source. Create a topic branch. Do not assume this handoff's code observations are still current. Identify and reuse already-working code before editing. Preserve ALL existing features (bookmarks, folders, password wallet/autofill/import, download destination and portal functionality, reader/printing/PDF, Shields, independent installed web apps, notifications, keyboard shortcuts, new-tab shortcuts, privacy, Flatpak, Windows paths). No extra telemetry, account, network service, database, or Chromium subprocess. Keep the low-RAM identity of Reyva.

**Delivery phases:** (1) audit and establish reproducible baselines; (2) implement seven targeted improvements plus Smart Dashboard and welcome flow in small reviewed commits; (3) test and find bugs; (4) fix all release-blocking bugs; (5) execute clean ReyOS/Flatpak and Ubuntu .deb build checks and local website preview; (6) produce reports, candidate artifacts, checksums, and a RELEASE_NOTES_DRAFT.md, but **do not release**. Provide a clear go/no-go verdict.

## 1. Verified code context (recheck against latest HEAD)

- Core: `reyos-packages/reyos-browser/files/usr/share/reyos/browser/main.py` is the PySide6/Qt WebEngine backend. `qml/Main.qml` owns tabs, `StackLayout`/`Repeater`, and lifecycle management. `qml/components/NewTabPage.qml` already implements the custom new-tab screen and editable shortcuts. `qml/AppWindow.qml` runs separately installed web apps.
- Existing low-memory behavior: `BrowserBackend.lowMemoryMode`, `toggleLowMemoryMode`; `Main.qml` `WebEngineView.updateLifecycle()` plus a 120,000 ms inactive timer that freezes only when recommended, then a 480,000 ms timer and recommended discard. Active and keep-alive/pinned tabs remain active. **Do not reimplement or shorten blindly.** Check active audio/video, WebRTC, downloads, form data and web apps before any tweaks.
- Search engines currently DuckDuckGo and Startpage; avoid promising Google/Bing unless deliberately implemented.
- Existing bookmark HTML import (`chooseBookmarkImport`, `importBookmarks`, `bookmarkImportFinished`), password CSV import (`choosePasswordImport`, `importPasswords`, `passwordImportFinished`), stored shortcuts (max 12), `installedWebApps` list. Import logic must be reused, not cloned.
- Existing default browsing profile is off-the-record / nonpersistent cookie storage. Installed web apps have separate persistent session behavior. Never inadvertently mix their profiles.
- ReyOS Arch package `reyos-browser` currently serves as a Flatpak launcher, not a standalone native Arch Qt build. Packaging: `reyos-packages/reyos-browser/PKGBUILD` and `arch-flatpak/usr/bin/reyos-browser`. Linux Flatpak ID `com.reyapps.Reyva` with signed repo, manifest `flatpak/com.reyapps.Reyva.yaml`; Ubuntu `.deb` built with `reyos-packages/reyos-browser/debian/build.sh`; website `website/index.html`; related `flatpak/README.md`.
- Known Flatpak Qt/PySide runtime incompatibility: 2026-11-16 `docs/fixes.md` describes a guarded automatic rebuild script `tools/reyva-flatpak/rebuild.sh` and timer; cannot guarantee a successful build when upstream runtime and BaseApp are temporarily mismatched. Do not bypass build/startup checks or treat watchdog rebuild as proof of compatibility.
- Docs version may be stale (`docs/browser.md` says 0.1.10 while November fixes discuss 0.1.12). Verify and reconcile version markers; do not invent a version.

## 2. Scope: seven improvements — avoid feature bloat

### A. RAM optimization / leak prevention (top priority)
- Profile TOTAL process-tree memory, including parent, QtWebEngine renderer/GPU/utility processes; for Linux report aggregate PSS (`smaps_rollup` if available) and RSS as secondary metric, not parent-only Python RSS. Include CPU and startup timings on a named machine.
- Establish baseline before changes with blank tab, 1, 5, 10, and 20 tabs; 5 mixed sites, long browsing session, YouTube playing, one installed web app, tab open-close repeat, switching away/back. Warm and cold starts; run >=3 repetitions with identical workload/versions, median and spread.
- Find actual retained objects/timers/JS connections/referenced views; fix leaks only with evidence. Pay special attention to `StackLayout`/`Repeater`, `WebEngineView` disposal, delayed callbacks, screenshot/favicon/icon loading, and signal connections. Verify OS process exits after closing browser/web apps.
- No periodic heavy memory sampling in production. No extra engine view for dashboards. No regression exceeding 10% idle PSS or meaningful tab-switch latency absent explicit documented rationale; report if baseline variance prevents a conclusion.

### B. Faster startup / lower idle CPU
- Profile launch to interactive first tab; avoid blocking UI thread with unnecessary startup I/O, network refresh, repeated file scans, favicon extraction, or eager dashboard indexing. Defer optional work until needed; handle offline launches. Confirm no visual flashes and no abandoned background threads.

### C. Existing intelligent tab sleeping: refine, don't duplicate
- Preserve 2-minute freeze / later discard defaults until tests justify change; honor engine `recommendedState`; protect active tabs, pinned/keep-alive tabs, active media, downloads, conferencing, unsaved forms as feasible. Test QML lifecycle event order and reactivation. Show sleeping state clearly. Dashboard must never wake tabs just to search their titles.

### D. Crash recovery without weakening privacy
- Default must remain private-by-default. Implement opt-in **crash-only** restoration of URL/title/tab order, never cookies, form fields, password values, or page content. Encrypt/limit exposure as appropriate; delete recovery file on clean exit, after successful restore/decline, and when feature disabled. Provide a clear on/off setting, metadata retention description, and a Restore/Discard choice only after genuine unclean shutdown. Do not persist session data for users who did not opt in. Atomic writes + corruption handling; test power interruption, multiple processes, and rapid tab changes. Ensure normal exit does not leave recoverable URLs.

### E. First-time welcome wizard and migration
- 4–5 compact skippable steps: Welcome/privacy explanation; bookmark HTML import with browser-specific export help; optionally password CSV import with conspicuous warning that plaintext CSV is sensitive and should be deleted securely afterward; choose existing DuckDuckGo/Startpage; finish and browse. Display actual import results/errors. Do not mislead that direct Safari/Chrome database import exists. Reuse existing backend signals/slots and system wallet logic.
- Store `onboardingCompleted` per-user in existing `settings.json` using existing atomic save method; do not show again on upgrades or installed web-app windows. Existing configured users (e.g. bookmarks or settings present) must not unexpectedly be forced through wizard. Provide Settings > Replay Welcome. External URLs passed at startup must not be lost. Offline working. On cancel/error, no data lost.

### F. Optional vertical tabs + fast tab search
- User-selectable normal horizontal strip vs vertical sidebar; horizontal default. Reuse existing `tabs` model and selection/close/reopen functions; do not create extra WebEngineViews or duplicate page state. Tab search should filter metadata for currently open tabs, focus selected existing tab, never open duplicate, and not wake discarded tabs until selected. Keep groups optional and lightweight; avoid complicated persistent groups on first iteration. Keep keyboard navigation and accessibility working.

### G. Shields/permissions improvements
- Improve the existing Shields UI: last list update, status, per-site controls, concise explanation of blocked requests, diagnostics for site breakage, and refresh failure messages. Do not imply content-block guarantees that do not exist. Permissions center should reflect actual Qt permission behavior and persist overrides only if chosen; never silently grant microphone/camera/location/clipboard. Ensure site-origin matching is accurate, no unsafe wildcard permissions, all states resettable. Avoid any new background tracker/network telemetry.

## 3. Smart Dashboard — requested behavior

Upgrade `qml/components/NewTabPage.qml` into a visually clean **single New Tab Dashboard**. Preserve existing shortcut tiles and search. Add clearly labeled **Open Tabs**, **Bookmarks**, **Installed Web Apps**, and **Web Search** results, plus an All view. Search field should return local results promptly without separate indexing service. Keep UI sparse by default; only populate rich results on user interaction. No remote queries or previews while typing unless normal search is explicitly submitted.

**Open tabs:** list existing tab title/favicon/url (as available) from the *current* tabs model; click switches `tabBar.currentIndex` to the exact existing tab (not `openInNewTab`), including background frozen/discarded tabs. Closing/renaming/grouping tabs updates results immediately. Avoid stale indexes and display only live tab data. Preserve focus/keyboard behavior.

**Bookmarks:** use `browserBackend.bookmarks` and existing `openBookmarkUrl` appropriately. URLs must be validated and respect privacy profile. Optional bookmarking actions are not required for first pass.

**Installed web apps:** read `browserBackend.installedWebApps` but verify its existing entries only expose ID/name/icon/comment; they do NOT necessarily include the original launch URL. **Do not infer launch commands or naively open them in a normal private browser tab.** Add a secure backend `launchInstalledWebApp(app_id)` only if needed, with strict app ID validation, lookup against verified installed entries, platform-specific launcher execution, and Flatpak portal constraints. Existing web apps must launch in their own app process/window with their own persistent profile; test ReyOS/KDE portal and Ubuntu `.deb` separately. Handle missing/removed launchers, duplicates, app icon errors, and unsupported portals gracefully. Distinguish an installed app from an open normal tab. Do not trigger launch during typing/search result hover.

**Web search:** when Enter is pressed on a free-text query without explicitly selecting local result, use the current chosen search provider. Never leak local tab titles or installed-app metadata to remote search. Search ranking should prefer exact local matches while clearly distinguishing external web search. Support keyboard arrows, Enter, Escape, accessible labels, visually restrained theming, and empty states.

**Performance constraint:** no long-lived periodic scanning of desktop files, no new Chromium web view for results, no thumbnails or remote icons fetched merely by opening dashboard, no always-on listeners other than existing light QML model signals. Instrument dashboard idle CPU/PSS delta and compare against baseline.

## 4. Potential issues to AUDIT (not yet confirmed bugs)

These are source-derived concerns requiring reproduction before changes:
1. **Web app launching from dashboard is not implemented.** `installedWebApps` list contains id/name/icon/comment; existing manager UI appears to expose Remove, not a guaranteed Launch action. Need proper OS-specific secure launcher path and missing-launcher handling.
2. **Dashboard tab focus:** `openInNewTab(pageUrl)` appends a tab but does not explicitly select it; inspect all callers, Qt signal behavior and actual selection, especially dashboard actions. A tab-search hit must explicitly select existing tab.
3. **Tab sleep behavior:** current `updateLifecycle` restarts inactive timer on state transitions; verify freeze/discard timeline and that background audio, notifications, unsaved forms and downloads remain correct. Avoid claiming any fixed 10-minute discard if engine refuses it.
4. **Web-app list performance:** non-Flatpak property reads scan `.desktop` entries on demand. Verify no repeated disk scanning from new QML bindings; cache/invalidate on install/uninstall when needed.
5. **File URL construction for web-app icons:** manager builds `file://` from file path. Test spaces, Unicode, absolute paths, Flatpak sandbox visibility, missing paths; prefer correct QUrl/fromLocalFile semantics when bridging to QML.
6. **Version/release consistency:** browser doc version may differ from app/manifests/releases. Reconcile from HEAD.
7. **Flatpak Qt/PySide mismatch:** run both PySide import test and WebEngine offscreen startup; do not publish a runtime-incompatible build.
8. **Downloads and external file permissions:** regression tests for portal selected folders, removable media, downloaded-to-temp fallback, large files, cancel/retry, long filenames, PDF export, show in folder, low disk space; never turn a dashboard change into a download regression.
9. **Privacy boundary:** private tabs should not cross into persistent installed-app profiles; crash recovery, local search, bookmarks, and password import must not leak to logs or third parties.

For each bug identified: write an issue record with severity, environment, reproducible steps, expected/actual behavior, root cause, code diff, regression test, and test result. **Do not mark a suspected problem as fixed unless actually reproduced and retested.**

## 5. Mandatory quality/testing matrix

| Test group | Must cover |
|---|---|
| Unit | bookmark HTML import (duplicates/folders/malformed), password CSV validation, URL sanitization, search matching/ranking, safe app-id resolution, setting migrations/atomic writes, crash marker parsing, Shields allow/block logic |
| UI | first-run/skips/replay, tab switch without duplication, tabs frozen/discarded, web app launch vs normal tab, search keyboard UX, bookmarks, vertical/horizontal tabs, small-window layouts, themes, accessibility |
| Browser regressions | HTTPS, redirects, downloads/open/show/cancel, print/PDF, video playback/fullscreen/audio, reader, private session cleared on clean exit, saved passwords via wallet, permission prompts |
| Security/privacy | untrusted bookmarks/HTML, imported CSV handling, malicious app identifiers, launcher command injection, file paths/spaces, local metadata not sent to search engines, no persistent history by default |
| Performance | idle and tab counts 1/5/10/20; repeated tab churn; video and web apps; low-memory on/off; Dashboard before/after; compare PSS CPU time startup and renderer count |
| Stress | 100+ tab open/close cycles, crash during state save, malformed configs, offline operation, corrupted bookmark/password input, missing app launcher, platform-specific portal failure |
| Packaging | Flatpak sandbox and host launcher, Arch wrapper, Ubuntu .deb native execution, clean install and upgrade without data loss, runtime compatibility |

**Test environments:**
- ReyOS KDE Plasma actual installation: Arch wrapper launches Flatpak `com.reyapps.Reyva`. Test a clean profile AND an existing user's upgraded profile; check install-as-app DynamicLauncher support, theme extraction, KWallet, URLs passed from launchers, and update behavior.
- Ubuntu 24.04 (or latest explicitly supported): build and install actual `.deb` on a clean test machine/container; GUI smoke tests on a real desktop session, not container-only. Test system keyring, GNOME/KDE variations, launchers, file picker and download paths. **Important:** stock Ubuntu 24.04 Flatpak DynamicLauncher may fail due to AppArmor/user namespace restrictions documented in `flatpak/README.md`; distinguish environment restriction from Reyva defect and ensure graceful guidance.
- Any-Linux Flatpak: manifest lint and repo lint; sandbox file/portal permissions; host Web Apps where supported.
- Windows: at least code review and smoke test or explicitly mark **not tested**; don't silently break existing Windows support while doing ReyOS/Ubuntu work.

**Performance benchmark report:** save test hardware model, RAM, CPU, GPU, distro/kernel, Flatpak runtime, Qt/PySide versions, power profile, URLs and steps. Measure baseline and final in same environment. Report median + variance, not invented targets. If performance regresses, investigate before approval.

## 6. Implementation process and release gates

1. `git fetch origin`; create `feature/reyva-lightweight-dashboard-qa` from latest main; avoid modifying unrelated ReyOS components.
2. Audit files/behavior, fill `docs/reyva-audit.md` with implemented vs missing vs broken vs not reproducible, test plan and baseline metrics. Mark blockers.
3. Add pure Python testable helper functions where appropriate; write tests before/with fixes. Make QML UI changes modular; avoid growing `Main.qml` unnecessarily.
4. Implement in small sequential commits (first-run, dashboard, tabs, stability, Shields, tested optimizations). After each milestone run lint/compile/smoke/performance checks.
5. Run full regression and reproduce/fix bugs; loop until no P0/P1 known release blockers. P2 issues must be listed with explicit owner acceptance. Do NOT silently skip or edit tests to pass.
6. Candidate builds only: locally build Flatpak using `flatpak/README.md`'s documented commands; verify matching Qt/PySide imports and offscreen WebEngine startup; build Ubuntu `.deb` via `debian/build.sh <version>` and test clean install/upgrade; confirm ReyOS Arch wrapper properly launches candidate Flatpak. Keep signing keys private, never log credentials. Build website locally and verify links, checksums and version information. **Do not push to signed live repo or website.**
7. Generate release notes, complete per-platform QA report, PSS charts/tables, checksums and manifest of built artifacts; mark PASS/FAIL/NOT TESTED explicitly.
8. Present owner with summary and a proposed release sequence: **(a)** approved code merge, **(b)** approved signed Flatpak candidate for ReyOS and generic Linux, **(c)** approved Ubuntu .deb, **(d)** approved website download links. Wait for explicit authorization at each public publishing action.

## 7. Precise acceptance criteria

- All seven areas reviewed, implemented only where missing/justified, and evidenced with before/after tests; no duplicated Low Memory Mode.
- Dashboard search correctly switches to existing open tab; bookmarks open via existing browser flow; web apps start in isolated installed-app window, never as regular private tab; search engine choices remain functional.
- No unexpected browsing-data persistence. Opt-in crash recovery does not save session data without consent; clean exits remove recovery metadata.
- All core browser capabilities continue to pass regressions; installed-app logins persist only in their own app profile.
- No P0/P1 known bugs; any remaining lesser issues documented. Flatpak Qt/PySide compatibility validated. Build and upgrade tests documented for ReyOS and Ubuntu.
- Idle memory and startup performance measured; deviations from baseline documented and within approved threshold (default investigate any >10% idle PSS regression).
- First-run guide appears once appropriately, supports HTML bookmark imports, and can be replayed.
- Final output includes changed-file inventory, commits, screenshots or screencast, test logs, baseline/results, failure list, candidate file paths and SHA256, docs updates, and release **go/no-go**. DO NOT say "all tests passed" unless tests truly ran.

## 8. Claude's final report template

- **Base commit / candidate commit:** ...
- **Version and platforms built:** ...
- **Features implemented / reused / deferred:** ...
- **Bugs found, reproduced, fixed, unresolved:** table with IDs, severity, verification
- **Tests:** command, environment, PASS/FAIL/NOT TESTED, logs
- **Performance:** PSS/RSS/CPU/startup before and after, variance, observed impact
- **ReyOS Flatpak:** build, install, update and launch results; portal/web apps/KWallet
- **Ubuntu .deb:** clean install, upgrade, GUI smoke results
- **Website preview:** paths/links verified; no live change
- **Files and SHA256:** ...
- **Release verdict:** GO / NO-GO and justification
- **Requires owner approval before publishing:** explicit yes

## 9. Copy/paste kickoff for Claude Code

> Read `REYVA_CLAUDE_IMPLEMENTATION_TEST_BUGFIX_HANDOFF.md` completely and inspect the latest `Reypaulino/ReyOS` main branch. Perform a baseline/bug audit first and verify which requested features already exist, especially memory management. Implement the missing seven improvements plus a lightweight unified New Tab Dashboard (open tabs, bookmarks, web search, installed web apps in their own windows) and first-run guided import. Find and fix reproducible bugs, rerun automated and GUI regressions, measure total RAM/CPU/startup before and after, and prepare TESTED LOCAL candidate builds for ReyOS Flatpak/Arch wrapper and Ubuntu .deb plus a local download-website preview. Preserve privacy and Windows compatibility. Do not publish, merge, tag, sign/push public releases, or update the live website without my approval. Report any remaining blockers clearly.