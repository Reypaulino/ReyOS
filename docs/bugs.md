# ReyOS — Known Open Bugs

Bugs that are confirmed real but not yet fixed. See `fixes.md` for the ones that *are* resolved.

This file was rewritten from scratch on 2026-08-18 after a full audit of the working tree (most of the source had drifted weeks ahead of the previous version of this doc, which still described things that were already fixed or no longer applied). Anything not carried forward from the previous version was either confirmed resolved (moved to `fixes.md`) or could no longer be confirmed as still true and was dropped rather than carried forward as stale guesswork.

**2026-10-08 verification pass:** see `BUG_VERIFICATION_REPORT.md` for what was re-tested and how. Entries below carry a "Status 2026-10-08" line where they were checked; resolved entries moved to the "Resolved" section at the end.

## Remote Play: limits and untested parts (2026-10-27)

control-center-gui 1.0.0-146, GitHub #22:
- No real stream has been run yet (VM: pairing and app list only). Apple TV, iPhone, Tailscale, the HD 630 VA-API encoder and controllers over Moonlight are the owner's tests (`docs/remote-play-testing.md`).
- Capture needs an unlocked, logged-in session with the screen on (KWin capture). Lid closed or locked = nothing or the lock screen.
- Sunshine as a user service has no file capabilities (no KMS capture, "Failed to gain CAP_SYS_ADMIN" in its log is expected) and no CAP_SYS_NICE (EGL priority warning).
- `sunshine` in reyos-local is a fixed upstream build: it isn't rebuilt when Arch's libraries change soname (miniupnpc, libmfx…), and the stable check only tests reyos-* packages. Recheck `ldd /usr/bin/sunshine` when promoting a snapshot.

## Login screen: Xorg crashed at boot with an HDMI screen; no login attempt reached SDDM (2026-10-26, laptop)

Laptop, Oct 26 09:01: the greeter's Xorg segfaulted in `RRTellChanged` (RandR) 10 s into boot and took `sddm-greeter-qt6` with it; SDDM restarted both and the greeter came up on eDP-1 and HDMI-1. For the next 30 minutes the journal shows no authentication attempt at all (not even a failed password), so typing didn't reach the password field, probably because keyboard focus was on the other screen. First boot with the HDMI screen attached. Not reproduced, not fixed. Cores: `/var/lib/systemd/coredump/core.Xorg.0.*` and `core.sddm-greeter-qt.*` on the laptop.

## ReyOS Scan v1: known gaps (2026-10-25)

Not bugs in what shipped, but limits to keep in mind (control-center-gui 1.0.0-143, GitHub #17):
- GUI (Security card, Quarantine window, ReyOS Games scan dialog) not yet clicked through; backend tested on the Dev VM only.
- No weekly scheduled scan, no Dolphin "Scan with ReyOS Scan", no system-file check (`pacman -Qkk`), no scan-result cache by hash: every Add PC game re-scans.
- System files and other users' files can't be quarantined (runs as the user; no polkit helper yet).
- Add PC game's pre-run check covers programs/scripts/archives only, not game data files; archives are scanned within ClamAV's own limits (no extra zip-bomb guard).
- Each scan spends ~12 s loading the definitions (no clamd, by design).

## Low free space isn't warned about (2026-10-23, laptop)

The laptop's ReyOS root reached 12 MB free before anyone noticed; Control Center has no low-disk warning (e.g. under 2 GB) and "Remove old packages" only does `-Sc`. Not fixed.

## Stable check doesn't build the NVIDIA 580 DKMS module (2026-10-25)

The weekly snapshot check installs reyos-* only; whether `nvidia-580xx-dkms` still builds against a new snapshot's kernel isn't tested, so a promotion could ship a kernel that leaves the laptop's NVIDIA card without a driver. Not fixed.

## Desktop sharing logins fail on current Arch (FreeRDP 3.32 + krdp 6.7.5)

Added 2026-10-19 (laptop). Every login from Windows App/an RDP client is refused: krdp log `ntlm_fetch_ntlm_v2_hash: Could not find user in SAM database` → `SEC_E_NO_CREDENTIALS`. FreeRDP 3.32 regression (FreeRDP #13567/#13688, KDE bug 526928), fixed in krdp MR !248, not yet in Arch. Laptop workaround: freerdp 3.31.0-1 from the Arch archive + `IgnorePkg = freerdp` (since lost to a reinstall). Not fixed in ReyOS: consider holding freerdp in the stable channel until krdp ships the fix, or a Connect note. Also: with `SystemUserEnabled=true` the password asked for is the ReyOS login password, not the one set in Connect's dialog — Connect's text should say so.

Status 2026-10-20: stable now ships krdp 6.8.0 + freerdp 3.32.2 (snapshot 2026/10/19), which may include krdp MR !248. Couldn't test from the Dev VM (krdpserver exits at once when started over SSH). **Retest on the laptop** with a real RDP client after Update everything.

## Games: PCSX2 swaps face buttons for third-party pads in Xbox mode

Added 2026-10-15 (laptop). The user's pad switches between Xbox mode (`045e:02e0`) and PlayStation mode (`054c:05c4`, DualShock 4). In Xbox mode, PCSX2's `SDLControllerEnhancedMode = true` (HIDAPI, "Xbox One Controller") mixes up the face buttons; host SDL3 sees them right. PlayStation mode is fine. Not changed in code: decide whether ReyOS should turn Enhanced Mode off for non-Microsoft "Xbox" pads. The laptop's PCSX2.ini has it off now (set by hand during testing).

## Unverified from the 124 batch

Wallpaper fix on a fresh install (needs a new ISO), Azahar (3DS) controls with a real game (written at 3DS launch; not yet on the laptop's real config), player 1 with two pads in PCSX2 (`SDL-<n>` follows connection order).

Status 2026-10-20: the wallpaper fix was confirmed on the 2026.10.16 ISO's VM install (slideshow after reboot). Still unverified: Azahar controls with a real game, player 1 with two pads in PCSX2.

## Bottom panel stays light after switching Light → Dark

Added 2026-10-08, Dev VM only. Driving `applyLookAndFeel()` Light → Dark → Light → Dark: after each Dark step the bottom panel stayed light (still light 60 s later with a freshly restarted plasmashell), while `kdeglobals` held the dark `ReyOS` scheme and the Plasma theme was `ReyOS` (panel transparency 85%). It was dark before the test. Not root-caused; check on real hardware first (the VM renders in software).

## Reyva: first page opened at startup can load half-styled (CSS/images/fonts missing)

Seen 2026-10-05 and 2026-10-06 on the Dev VM. `reyos-browser https://kde.org` (or the Flatpak with the same URL) right after starting showed kde.org with no CSS (plain blue links, raw lists), or with CSS but no banner image and no Inter webfont. Hit in the Flatpak on its first launch after a fresh install (twice) **and in the native build** run from source (2026-10-06), so it is not Flatpak-specific. A DevTools reload of the same tab loaded all 62 requests with 0 failures, and later launches usually render fine, so it looks like something about the very first load at startup (start URL loaded before the profile/interceptor/scripts are fully set up?). Not root-caused. Matters because links opened from other apps take exactly this path.

Status 2026-10-08: not reproduced in 3 cold starts with `https://kde.org` on the Dev VM (Flatpak 0.1.1); the original trigger (first launch right after a fresh install) wasn't recreated. No fix exists. Kept open.

## ReyOS Reader: PDF viewer header toolbar becomes nearly invisible after clicking into page content

Found live (2026-09-12) while investigating a different PDF complaint ("also in the pdf dont go under the tools like zoom or soenthing") — likely what the user actually meant by that report, but not yet confirmed as the same thing since it wasn't re-raised after the pagination/annotation work that session. Reproduced: open a PDF, zoom in/out/fit-width all work correctly in isolation, but after clicking into the page content area and navigating with `Page Down` a couple of times, the header toolbar (Back button, title text, page counter/nav, zoom controls) renders at very low contrast, nearly invisible against the background, while the PDF page content itself displays normally. Not root-caused — no theory recorded yet, this is a bare repro. `PdfReaderPage.qml`'s header changed shape twice since this was found (find bar + annotation toolbar buttons added, then the `PdfAnnotatedMultiPageView` fork) — re-confirm this still reproduces against the current header layout before assuming the same fix location applies.

## Launched apps sometimes never get a taskbar entry, on a real fresh install

Confirmed live (2026-08-24) on a genuine fresh Calamares install of `ReyOS-Test`, first time this bug class has an actual real-install repro rather than a theory (see the "App launcher shows no per-app icons" entry below, which is related but distinct — that one's about wrong/missing icons, this one is about the taskbar entry not existing at all). ReyOS Browser and Dolphin, opened from the app launcher, render their window on screen correctly but get no Task Manager button. Ruled out so far:
- **Not Wayland-specific**: reproduced identically after explicitly selecting the "Plasma (X11)" SDDM session, not just the default Wayland one.
- **Not a pure first-boot race**: initially looked like one (a relogin made the browser's taskbar entry appear correctly once), but a later same-session close+reopen of the browser reproduced the missing entry again, and a full fresh reboot reproduced it again too. So it's intermittent/recurring, not "broken once at first boot, fixed forever after."
- Separately, one pinned taskbar launcher (likely Dolphin's) shows a **blank/generic icon** instead of its real one — could be the same root cause as the Kickoff icon bug below, or unrelated; not disentangled yet.
- Same session, later report: pinned "favorite" launcher icons in the taskbar not showing at all (not just the wrong icon) — likely the same underlying bug, not confirmed as a separate issue.

First diagnosis attempt via terminal relay (no working SSH to a real install — see the SSH-timeout entry below) hit a dead end: `wmctrl` isn't installed, `journalctl --user -b | grep -i taskmanager` ran but found nothing, and `journalctl --user -u plasma-plasmashell -b` reported no journal files exist at all for that scope.

**Second attempt, same day, got real shell access via QMP keyboard input (typed into Konsole through `virsh qemu-monitor-command --hmp "sendkey ..."`, screenshotting after each command) — found real, concrete evidence:**

- The panel's task widget is `org.kde.plasma.icontasks` (Icons-only Task Manager), not the classic `org.kde.plasma.taskmanager` — a legitimate, common choice, not inherently broken. Confirmed via `~/.config/plasma-org.kde.plasma.desktop-appletsrc`: `[Containments][20][Applets][22]` → `plugin=org.kde.plasma.icontasks`.
- Its `launchers=` config is correctly populated: `applications:systemsettings.desktop,applications:org.kde.discover.desktop,applications:reyos-control-center.desktop,applications:org.kde.dolphin.desktop,applications:reyos-browser.desktop` — five real pinned apps including Dolphin and ReyOS Browser. So the *configuration* is right; whatever's wrong is in how icontasks renders/tracks against that config at runtime.
- Live screenshots taken throughout the session showed the actual visible icon count fluctuating between 3 and 5 for the *same* unchanged config — sometimes showing only 3 (kickoff + 2), sometimes more — with no consistent pattern found tying the count to which apps were actually running.
- `plasmashell` itself is healthy: single stable process (`ps -o pid,etimes,cmd -C plasmashell` showed one process, ~69 min uptime matching session uptime, no crash-restart), and `coredumpctl list` showed no crashes. So this isn't a crash-loop — icontasks is up and rendering *something*, just not consistently reflecting either its own static `launchers=` list or actually-running windows (Konsole, opened live during this diagnosis, never got an entry either, confirmed via direct observation, not just the browser/Dolphin from earlier).
- A dimmed "▾"-style icon visible in the panel might be icontasks' own overflow indicator (shown when there's insufficient width for all icons) — but the panel has substantial unused blank space, so a real width-overflow seems unlikely; not confirmed either way, a mouse click aimed at it (via QMP `mouse_move`, using the 0–32767 absolute-pointer scale, not raw pixels — first click attempt failed silently by sending raw pixel coordinates instead) landed inconclusively.

**Next steps if resumed**: the QMP-keyboard-input + screenshot loop is a real working method now for driving a real install without SSH (see the recipe above) — reuse it rather than re-discovering it. Worth trying: `qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript` with a script that dumps the task manager's actual model contents (window list icontasks itself sees), and precisely locating/clicking that overflow-style icon to see what it actually reveals.

**Third attempt (2026-08-25)** — resumed the exact same live diagnostic session (unlocked it, same Konsole/appletsrc state still on screen) and tried two of the leads above; both were dead ends, but ruled out real possibilities rather than being wasted:
- **The session is genuinely Wayland** (`kwin_wayland_wrapper --xwayland` confirmed via `pgrep -a kwin`), not X11 — despite the "Not Wayland-specific" note above (that was about *reproducing the symptom* under an explicitly-selected X11 *SDDM session*, a different kwin binary than whatever this particular boot happened to use; no contradiction). This matters because it ruled out a detour: `xprop -root _NET_CLIENT_LIST`/`_NET_CLIENT_LIST_STACKING` both came back completely empty despite ReyOS Browser and Konsole windows visibly on screen — looked like a huge lead at first, but it's an XWayland-only view and native Wayland clients (which these almost certainly are) never populate it at all. Not a real finding, don't re-chase this angle without first confirming the apps are actually running as XWayland clients.
- **`qdbus6 org.kde.KWin /KWin supportInformation`** (KWin 6.7.4 in this build) no longer includes a per-window list (`Caption`/`resourceClass` etc.) at all — older KWin versions had a "100 Windows" section in this dump; it's been dropped upstream. Confirmed by pulling the full 276-line dump (via a temporary `python3 -m http.server` on the VM, `curl`'d from the host — much faster than screenshot-per-command; see the `ufw`-blocks-everything finding just below for why that needed `sudo ufw disable` first). This diagnostic path is a dead end on this KWin version; the earlier-suggested `evaluateScript` route is still unexplored (this session tried the D-Bus supportInformation shortcut instead, didn't get to writing an actual Plasma JS script).
- **`sudo journalctl -b --no-pager | grep -i plasmashell`** — only 13 lines total for the whole session, all early-startup noise (expected `MESA-EGL: warning: egl: failed to create dri2 screen` from this VM having no GPU passthrough — compositing runs on `llvmpipe` software rendering, confirmed via the KWin support dump's `OpenGL renderer string: llvmpipe`; a portal-registration failure; a couple of deprecated-API notices). Nothing resembling a task-manager/icon error anywhere in the journal, at any point — reinforces the earlier "plasmashell is healthy, not crashing" finding rather than adding a new lead. `journalctl --user` (no `sudo`) still reports no journal files at all on this live session, same as the first attempt — always use `sudo journalctl` (system journal) on this build, not `--user`.
- **New, unexplored possibility worth flagging**: compositing is 100%-software (`llvmpipe`, no GPU) in this VM specifically (no `virgl`/GPU passthrough configured on the libvirt domain). A software-rendered compositor under load is a plausible source of the kind of inconsistent, no-error-logged, timing-sensitive rendering glitch this bug describes — worth keeping in mind that this exact symptom might be partly or wholly a VM-testing artifact rather than something real (even low-end) hardware would hit, though ReyOS's target audience (older hardware) means it's not safe to dismiss either. Not tested on real hardware at all yet.
- Also hit, unrelated to the bug itself: found two separate `konsole` processes running (`pgrep -a konsole` → two PIDs) while only one Konsole window was visible on screen — not investigated further, could be nothing (e.g. a leftover helper process), but noted in case it recurs and turns out to correlate with missing taskbar entries for that app.

**Fourth attempt, same session (2026-08-25) — likely found the real root cause class, via KWin's built-in Debug Console instead of scripting:**

`qdbus6 org.kde.KWin /KWin org.kde.KWin.showDebugConsole` opens a live GUI (Windows / Input Events / Input Devices / OpenGL / Keyboard / Clipboard / Effects tabs) that's much more useful than either of the two dead-end diagnostics above — it lists every window KWin actually manages, grouped by protocol, with a live property inspector (click any window in the tree to see every property KWin computes for it: `hidden`, `frameGeometry`, `iconGeometry`, `desktopWindow`, `dock`, etc.). This is a real repro, not a theory:

- The second, invisible `konsole` process from the previous bullet turned out to be a real managed window: `~ : systemctl — Konsole` (a leftover from an earlier diagnostic session's `systemctl` command), fully present in KWin's Wayland Windows list, with `hidden: false`, `minimized: false`, a completely valid on-screen `frameGeometry` (`184,147 911x496`, well inside the 1280×800 display), and even a valid taskbar `iconGeometry` (`92,760 48x40` — inside the panel's own bounds). By every property KWin itself reports, this window should be both visible on screen *and* have a working taskbar icon. **It was neither** — never appeared in any screenshot, the whole time it showed up in this list.
- Independently, partway through this same debug-console session, **the entire bottom panel stopped rendering** — not just its icons, the whole 1280×40 dock bar vanished from every subsequent screenshot, leaving plain desktop background where it should be. `qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "print(panelIds.length)"` still returned `2` (Plasma's own containment model is intact — this is **not** a recurrence of the separate "Live-boot session sometimes creates zero Plasma panels" bug above, which is about panels never being created in the first place). Found the actual panel object in the Debug Console's Wayland Windows list (a `KWin::LayerShellV1Window`, `bufferGeometry: 0,760 1280x40`, `dock: true`) and it, too, reports `hidden: false` with a fully valid geometry — KWin considers it a real, visible, correctly-positioned surface. It simply isn't being painted.

**Working theory, now well-supported by two independent repros in one session**: this isn't a task-manager-specific bug at all. It's a **KWin/Wayland compositor paint bug** — the window/surface model (what KWin *thinks* exists, where, and whether it's hidden) stays internally correct, but the actual compositing/damage-tracking pipeline sometimes fails to include a valid surface in the painted frame, with no error logged anywhere. This would fully explain the original symptom (icontasks' displayed icon count fluctuating against an unchanged, correctly-populated `launchers=` list — each "missing" icon may be a real taskbar entry that just isn't being painted that frame) as one instance of a broader class that also hit a plain app window and, independently, the panel itself. Compositing on this VM runs entirely on `llvmpipe` (software rendering, no GPU passthrough — see the previous attempt's finding); a software-rendering-specific race in KWin's repaint scheduling is the leading suspect, but not confirmed, and not yet tested on real hardware.

**Next steps if resumed**: try to force a full compositor repaint while a "stuck invisible" window/panel is reproduced (switching virtual desktops, toggling a `kwin --replace`, or resizing the output) and see whether it recovers — establishing whether this is a one-way stuck state or something that self-corrects would narrow this down a lot. Also worth checking KWin's `OpenGL` debug-console tab (frame timing / dropped-frame counters, if it exposes any) next time this reproduces live, and trying to correlate the panel's disappearance with a specific trigger (it happened shortly after repeatedly opening/closing the Debug Console dialog and using the mouse wheel inside it in this session — could be coincidence, or could mean opening/closing an internal KWin window is itself capable of corrupting the damage/repaint region tracking; not tested in isolation).

**Fifth attempt (2026-08-26)** — resumed the same still-alive `ReyOS-Test` live-boot diagnostic session (again unlocked, same Konsole history from the fourth attempt still on screen, confirming this domain has now sat live across three separate sessions without a reboot). Caught the icon count visibly fluctuating in real time this session (4 icons → 2 icons → 3 icons across consecutive screenshots, taken seconds apart with no user action in between other than typing an unrelated command in Konsole) — a live repro, not a theory.

- **Tried the "next step" from the fourth attempt: switching virtual desktops (`Meta+Ctrl+Right` then `Meta+Ctrl+Left`) while the icon count was in a degraded state — no effect.** Panel looked identical before and after. Either virtual-desktop switching doesn't count as a "damage/repaint" trigger for whatever's actually failing, or the stuck state isn't a one-way thing a simple repaint nudge fixes. Doesn't rule out `kwin --replace` or an output resize, still untried.
- **Significant refinement to the fourth attempt's "whole surface sometimes not painted" theory**: reopened the Debug Console and specifically inspected all three `KWin::LayerShellV1Window` entries this time (the fourth attempt found the bottom panel one; this session also checked the desktop-background layer and the top panel for comparison). The bottom panel (`bufferGeometry: 0,760 1280x40`, `dock: true`) reported `hidden: false` with fully valid geometry **at the same moment its visible icon count was degraded** — but unlike the fourth attempt's full-panel-disappearance repro, this time the panel *background itself* was clearly still painted (visible in every screenshot), just with fewer than the expected 5 task icons inside it. That's a meaningfully different symptom shape than "the whole surface stops being painted": here the panel container is being painted correctly, but something inside it — the `icontasks` applet's own icon list — isn't consistently rendering all its items. **This points more specifically at `icontasks`' own internal Qt Quick rendering/task-model (a `Repeater`/`ListView`-style delegate population issue, or a race in how it queries the window list it's supposed to reflect) rather than a generic KWin-wide compositor paint bug** — though the fourth attempt's separate full-panel-disappearance repro is still real and may be a related-but-distinct failure mode of the same underlying surface, not necessarily the same root cause as this one.

Status 2026-10-08: no fix exists and it has only ever been seen on VMs with software rendering; no observation from real hardware yet. Kept open.

**Next steps if resumed**: this narrows the search from "KWin compositor" to "the `icontasks` plasmoid's own task-icon rendering" — worth checking `org.kde.plasma.icontasks`' QML source (`plasma-desktop` upstream) for how it populates its icon `Repeater`/model from the window list, and whether there's a known timing/recycling bug in that specific applet on this Plasma/KWin version. Also still untried: `kwin --replace` or an output resize as a repaint trigger (only virtual-desktop-switch was tried this session, and it didn't help); correlating the fluctuation with anything in `journalctl -f` filtered for `plasmashell`/`icontasks` while actively watching the count change (not done this session — was mid-diagnosis when time ran out); and getting a clean read on whether this is `llvmpipe`/software-rendering-specific by testing on real hardware, still not done.

Status 2026-10-20: only ever seen on VMs with software rendering (Plasma 6.7.4), never reported from the laptop (real hardware, daily use). Recheck on Plasma 6.8 before spending more time.

## Control Center renders without icons/wrong theme if launched while the session is locked

Observed directly (2026-08-18): launching `python3 /usr/share/reyos/control-center/main.py` while the KDE session was still at the lock screen produced a window with the correct layout but a generic light Qt style and no sidebar icons at all. A second launch after the session was fully unlocked and settled rendered correctly (Midnight Copper dark theme, all sidebar icons present). Working theory, not rigorously isolated: Qt/Kirigami's icon-theme and platform-style lookup comes back empty if the app starts before Plasma's theming services are fully live (e.g., right at/before unlock), and it silently falls back instead of retrying. Low priority — no normal user workflow launches Control Center from a locked screen — but worth a real isolated repro if it's ever hit organically (e.g. via an autostart entry that races the lock screen on login).

## Welcome wizard sometimes needs a double-click on first launch

Launched via autostart with no window focus — the first click on any button gets consumed by the compositor just to raise/focus the window, never reaching the button underneath. A retry-based `requestActivate()` loop reduced but did not eliminate it. Leading theory: Wayland's activation-token model blocks self-activation for apps launched via a raw systemd/XDG autostart entry with no token-granting launch path, which would make this a platform limitation rather than something fixable purely in app code. Not revisited since first observed.

## Dark→Light theme switch, then Light→Dark again: color scheme stops actually applying to app content (new deeper bug found investigating the entry below)

Found live on the Dev VM (2026-08-27) while verifying the self-relaunch fix directly below. Sequence: Dark → Apply Light (worked correctly, confirmed via screenshot — window decoration *and* full content repainted light immediately) → Apply Dark again (window decoration went dark, but the sidebar/content stayed rendered in light colors). Kept re-checking for 15+ seconds — never self-corrected. Ruled out the relaunch code as the cause: killed the process entirely and cold-launched a brand-new instance (no relaunch chain at all) at the exact same point, and it *still* rendered light content with a dark title bar. `kreadconfig6` confirms `kdeglobals` genuinely says `ColorScheme=ReyOS` (dark) and `Icons/Theme=breeze-dark` at this point — so the config file is correct, but something in how a freshly-started Qt/Kirigami process resolves the actual color palette from that state is stuck on the previous (light) values. Not root-caused. Reproduce by flipping Light→Dark→Light→Dark a few times in one session and screenshotting after each `Apply`; worth checking whether `plasma-apply-colorscheme`'s own return code was actually 0 on the failing call, and whether this is specific to the Light→Dark direction or just whichever direction happens second in a quick sequence.

Status 2026-10-08: **still reproducible** after the 2026-09-29 Light/Dark rework. Real `applyLookAndFeel()` Light → Dark → Light → Dark on the Dev VM: both Dark steps returned success, `kdeglobals` dark (`[Colors:Window] BackgroundNormal=20,16,13`), page says "Active: ReyOS Dark", but the relaunched Control Center draws light content. It's Light → Dark specifically: Dark → Light rendered correctly both times. Control Center was also light all day before the test with the scheme set to Dark.

## Control Center's own window doesn't pick up a live theme switch — partially fixed 2026-08-27, see `fixes.md`

The relaunch-based fix below is confirmed working for the Dark→Light direction. The Light→Dark direction hit the separate, deeper bug entry directly above instead (window decoration updates, content doesn't) — that one is NOT yet fixed. Original notes, still accurate as background: sidebar icons were already confirmed to refresh fine after the `plasmashell` restart `applyLookAndFeel()` does; this bug was specifically about the window's own chrome/style.

## Live-boot session sometimes creates zero Plasma panels

Confirmed on 2 of 3 fresh `ReyOS-Test` live boots off the 2026-08-20 ISO (2026-08-20): `qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "print(panelIds.length)"` returned `0` minutes after login, with `plasmashell`/`kwin_wayland` both alive and initially consuming real CPU, then settling to near-idle by ~5 minutes uptime — genuinely stalled, not still mid-bootstrap (ruled out the documented "Plasma's first-boot bootstrap races any script" gotcha in `docs/DEVELOPER.md`, since idle CPU at 5+ minutes means nothing is still working on it). Confirmed NOT caused by `reyos-live-wallpaper.sh` (the live-ISO-only wallpaper script) — read its full source, it only writes wallpaper config via `qdbus6`/`kwriteconfig6`, never touches panels, and its own journal output was clean (the "malformed"-looking log lines turned out to just be its own `qdbus6 org.kde.plasmashell` healthcheck listing object paths, not an error). Root cause not yet found. Interestingly, Calamares itself renders fine as its own window regardless of this — so the stall is specific to Plasma's own panel/containment creation, not a general compositor failure. Reproduce again on the Dev VM (where SSH/shell access exists throughout, unlike a real install) with `journalctl -b` captured from second one to isolate what's failing during containment creation.

Status 2026-10-20: seen on the 2026-08-20 ISO only; not seen in the 2026.10.08/16/18 ISO tests. Recheck on the next ISO (first one with Plasma 6.8).

## Desktop Folder Settings dialog shows a stock "About" tab

Right-click desktop → Configure Desktop and Wallpaper opens Folder View's own settings dialog, which always includes a generic plugin "About" tab appended automatically by Plasma's own config-dialog framework — not specific to ReyOS's config, and no kiosk restriction found to suppress it. Purely cosmetic; disproportionate effort to fix (would mean patching Plasma itself). Deprioritized.

## Resolved

### Reyva: address bar blank when started with a URL — fixed in Reyva 0.1.11

The current tab now calls `syncCurrentSite()` when loading finishes. Checked in the Flatpak runtime with `https://example.com/a%20b?x=1&y=2`.

### Reyva couldn't save passwords on a fresh install (no default wallet) — fixed in reyos-sddm 1.0.3-19 (kwallet-pam)

Cause found on the laptop: no wallet existed and `kwallet-pam` wasn't installed. With it, a password login creates and unlocks `kdewallet`, and the Secret Service `default` alias resolves (Dev VM test, see `fixes.md` 2026-10-20). Reyva 0.1.11 also explains how to create a wallet when none exists (laptop patch 0003).

### Broadcom Wi-Fi driver wasn't built for the LTS backup kernel — fixed in reyos-boot 1.0.0-3

`linux-lts-headers` is now a dependency of reyos-boot (user's OK), so DKMS builds `broadcom-wl` for the LTS kernel too. Dev VM through the normal update: `dkms status` lists broadcom-wl for both `7.2.11-arch1-1` and `6.18.57-2-lts`, no ERROR line. Costs ~306 MB on disk.

### Mouse page: per-device settings lost at login on X11 — resolved by the move to Wayland (reyos-sddm 18)

Plasma 6.8 has no X11 session. On Wayland KWin reads the `[Libinput][vendor][product][name]` groups at login: checked 2026-10-20 on the Dev VM after a reboot, the PS/2 mouse came up with the saved `pointerAcceleration` 0.55 and natural scrolling on.

### Connect: phone not found because the firewall blocks KDE Connect — fixed in reyos-connect 1.0.0-22

Installing or updating reyos-connect now runs `ufw allow KDEConnect` once (marker `/var/lib/reyos/connect-firewall-allowed`, so a rule the user removes stays removed). Connect's Devices page already had "Allow in firewall" and a firewall check; Control Center 130's Firewall page also shows KDE Connect with an Allow button. Tested on the Dev VM: rule added on install, not re-added after removal on a second upgrade.

### Connect: KRDP sharing doesn't work in the X11 session — resolved by the move to Wayland

Wayland is the only session since reyos-sddm 18 (Plasma 6.8 dropped X11), so sharing is available again; Connect's X11 notice stays for completeness and now names the session "ReyOS Desktop".

### Connect: desktop sharing blocked by the firewall — fixed in reyos-connect 1.0.0-22

The Remote Desktop page warns when ufw is on and nothing allows 3389/tcp, with an "Allow in firewall" action (`reyos-admin firewall allow 3389/tcp`). Not automatic on purpose: RDP stays closed until the user decides to share. Tested on the Dev VM: warning shown, one click added `3389/tcp` (v4+v6), warning gone. The rule isn't removed on Stop sharing.

### Installer copied the live recovery autostart into new installs — fixed in reyos-calamares 1.3.6-56 (next ISO)

`shellprocess_live_cleanup.conf` now removes `reyos-recovery-launch.desktop` from the target's `/etc/skel` and home autostarts, and `/usr/local/bin/reyos-recovery-launch.sh`. Existing installs keep the harmless file.

### Laptop install: ReyOS root 97 % full — obsolete

The laptop's ReyOS was reinstalled on 2026-10-19 on a 42 GB partition.

### "unknown key '%INSTALLED_DB%'" warnings — old installs only, nothing to fix

Written into the local package database by the pacman that built ISOs up to ~2026-09-11; current ISOs don't produce it (laptop: 0 entries), and each package loses it when it is upgraded or reinstalled. The 2026-10-20 Plasma 6.8 update rewrote most of the Dev VM's entries.

### SSH to an installed system times out — by design

Installs enable ufw with deny incoming (`shellprocess_firewall.conf`), so SSH is dropped until allowed. Since control-center-gui 130 the Firewall page lists SSH as Blocked with an Allow button when sshd is running.

## Discover can't manage system packages or firmware

Added 2026-10-09, real laptop install (ReyOS-side agent's log check). Discover logs that its `packagekit-backend` and `fwupd-backend` fail to load (`libpackagekitqt6` / `libfwupd.so.3` missing), so it only handles Flatpaks. Probably intended (system updates go through Control Center), but Discover still shows the empty sections. Decide: install the two backends, or hide/remove them so Discover is clearly Flatpak-only.

Decided 2026-10-13: keep Discover Flatpak-only. System updates must go through Control Center (stable channel, `reyos-channel upgrade`); a working PackageKit backend would let Discover do partial upgrades around it. `fwupd-backend` starts working by itself if the user installs `fwupd` (offered in Control Center). The log lines are harmless.


Moved out of the open list after the 2026-10-08 verification; original text kept for history.

### Control Center: "CPU mode" showed "Fast (performance)" where the CPU has no frequency control — fixed in control-center-gui 126

Now says "Not available on this computer". See `fixes.md` 2026-10-16.

### Feature buttons did partial upgrades (`pacman -Sy` + `pacman -S`) — fixed in control-center-gui 126 / welcome 33 / update-channel 2026.10.10-2

Found by the architecture audit. See `fixes.md` 2026-10-16.

### Reyva: Show in Folder / Open Downloads Folder did nothing — fixed in Flatpak 0.1.7, `.deb` 0.1.0-123ubuntu1, Windows 0.1.0.109

Reported from the laptop 2026-10-15. Now uses the file manager's FileManager1 D-Bus service (file selected), with Qt's openUrl as fallback. Details in `fixes.md` 2026-10-15 (night). Not yet clicked on the laptop.

### Wallpaper slideshow replaced by one image after every reboot — fixed in control-center-gui 124 / reyos-calamares 50 (fresh installs need the next ISO)

Reported from the laptop 2026-10-15. The live ISO's wallpaper autostart was copied into installed homes. Details in `fixes.md` 2026-10-15 (night).

### Date · Time showed "Timezone: Unknown" on systemd 262 — fixed in control-center-gui 124

Found on the laptop 2026-10-15: `timedatectl show --property=A,B,C` prints nothing on systemd 262; Control Center now passes one `-p` per property.
 Fixes from 2026-10-09 are listed first (details in `fixes.md`).

### Reyva: fullscreen video didn't work — fixed in Flatpak 0.1.2, `.deb` 0.1.0-118ubuntu1, Windows 0.1.0.106

Reported from the laptop 2026-10-09. Neither `WebEngineView` enabled `fullScreenSupportEnabled` or handled `fullScreenRequested`, so every player's fullscreen button did nothing. Verified on the Dev VM desktop (real fullscreen, real Esc), and in a clean Ubuntu container (.deb); the ReyOS-side agent confirmed the code is in the laptop's installed 0.1.2 but didn't watch it on screen. Not exercised on Windows.

### Reyva: 720p+ video had no picture on Intel graphics — fixed in Flatpak 0.1.3 / `.deb` 0.1.0-119ubuntu1, **not yet confirmed on the laptop**

Reported from the laptop 2026-10-09 ("watching video does not work"). GPU-decoded (VA-API) frames couldn't be imported for drawing in the Flatpak's QtWebEngine 6.11.1 (`MailboxVideoFrameConverter`, GPU context lost; 812 of 816 frames lost, one SIGTRAP crash). Reyva now passes `--disable-accelerated-video-decode` on Linux. Verified on the Dev VM (software decode active after `flatpak update`) and by the ReyOS-side agent with the flag by hand (0 errors). Move fully to `fixes.md` once the laptop confirms with 0.1.3 installed.

### Control Center didn't show Flatpak updates, and hid why a Flatpak update failed — fixed in control-center-gui 1.0.0-120

Reported from the laptop 2026-10-09 (Discover showed the Reyva update, Control Center didn't; a disk-full update only said "Flatpak update failed."). "Check for updates" and the Flatpak page now list pending app updates with old → new versions, and failures name the cause. Verified on the Dev VM with a real pending update (Reyva rolled back to 0.1.2, plus Azahar from Flathub) through Update all. The disk-full message was only unit-checked.

### Published ISO 2026.10.01: install stopped with "Missing variables are: PK" — resolved by ISO 2026.10.08

Resolved 2026-10-08 (Verified Fixed in a VM): ISO `reyos-2026.10.08` (sha256 `a10737519802269985914f470c4b9707f8ffd26f855a722997e3a37ed78eadb7`, reyos-calamares 1.3.6-48) installed to completion ("All done.") with Erase disk in a UEFI VM (Secure Boot off, 4 GB RAM, 30 GB disk); first boot, Welcome "Skip for now", desktop, Control Center → Install updates ("there is nothing to do ✓ Updates installed") and a restart all worked. The installed disk had no live-session leftovers, the stable channel (2026/10/07) and today's package versions. Not yet installed on real hardware. 2026.10.01 stays published but is no longer the latest release.

Original entry:


Added 2026-10-08. The ISO on the GitHub Release (sha256 matches) contains `reyos-calamares` 1.3.6-44, whose `shellprocess_hw_drivers.conf` (`$PK`) and `shellprocess_live_cleanup.conf` (`$T`) use bare shell variables; Calamares substitutes those before bash runs and aborts on unknown ones. Both modules are in the exec sequence. Seen on real hardware on 2026-10-01 (`fixes.md`). Fixed in source by `f8e3530` (1.3.6-45, current 1.3.6-48 scans clean), but the ISO was uploaded ~2 hours before the fix and never rebuilt. Needs a new ISO; the release notes and website don't mention it.

### Installer's "available only from the live session" error dialog on installed systems — resolved (`5ec0b31`)

Resolved 2026-10-08 (Partially Verified): `reyos-launch-installer --autostart` exits silently when `/proc/cmdline` has no archiso parameters, and the installer's live-cleanup step removes the autostart file. On the real Lenovo install the launcher has the silent exit and its journal has no such dialog; not yet watched on screen. Note: `reyos-calamares` updates reinstall `/etc/xdg/autostart/reyos-installer.desktop` on installed systems, which is harmless because of the silent exit.

Original entry:


Confirmed live (2026-08-31) on a genuine fresh install: `reyos-installer.desktop`'s autostart (`X-KDE-autostart-after=panel`) fires unconditionally on every KDE session start, live or installed. The live-vs-installed *detection* itself is now fixed (see `fixes.md`'s "three live-session detection functions were all silently broken" entry) — the dialog now only appears because the `.desktop` file has no gate of its own and always launches the script, which correctly refuses and reports why. Still a jarring, repeated error dialog on every first login of a real install (twice in one session observed: right after login, and again after Welcome's branding-apply step) — a bad first impression even though nothing harmful happens. Real fix should gate the `.desktop` file itself (`OnlyShowIn`, or a condition keyed off the same cmdline check) so it doesn't autostart at all outside a live session. Not fixed yet.
