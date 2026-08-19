# ReyOS Browser

## Current Dev build

`reyos-browser` 0.1.0-43 is a native PySide6/Qt Quick application using Qt WebEngine (Chromium). It is not a Firefox wrapper and it does not require Firefox at runtime. It is installed and tested only on the ReyOS Dev VM; it has not yet been staged to the ISO repository or deployed to ReyOS-Test.

## User-verified behavior

- Private, in-memory browsing profile starts correctly.
- Downloads dialog opens.
- Download notifications appear in KDE.
- The Downloads-folder button and download save target use `~/Downloads` after the v0.1.0-30 path correction.

## Current features

- Tabs, keyboard shortcuts (`Ctrl+T`, `Ctrl+W`, `Ctrl+L`, `Ctrl+R`), navigation, and DuckDuckGo search fallback.
- GPU acceleration by default on real hardware; automatic software-rendering fallback inside virtual machines.
- Low Memory Mode, enabled for the current session by default: safely freezes inactive tabs after two minutes and may discard them after fifteen more minutes when Qt reports that they are safe to suspend; selecting a discarded tab reloads it. The `RAM` toolbar control toggles this mode.
- Off-the-record WebEngine profile, memory-only cache/cookies, blocked popup windows, and a visible session-only Allow/Block prompt for sensitive permission requests.
- Browser Settings panel: session-only DuckDuckGo/Startpage search choice, Low Memory Mode control, and live Shields status.
- Reader Mode converts the current tab into an article-focused view; selecting `Exit Read` or `Ctrl+Shift+R` returns to the original page.
- Private Session History shows up to 50 pages visited during the current browser run, can reopen a page in the active tab, and is cleared at exit or manually from its panel.
- Find in Page has an in-window search bar, match count, next/previous navigation, and `Ctrl+F`.
- Branded vector reload control with tooltip and accessibility name.
- ReyOS Shields v1: 21 curated network ad/tracker domains blocked before Chromium networking; master on/off toggle, live session blocked-request count, and per-site session-only exceptions; no persistence.
- Downloads manager with live byte progress, completed/failed/cancelled state, Cancel, Open File, KDE notifications, and standard Downloads location.
- Frozen (`❄`) and discarded (`◌`) markers in tab titles when Low Memory Mode changes their lifecycle state.
- Downloads dialog, KDE start/completion notifications, standard Downloads location, and folder opener.
- ReyOS blue active tabs, dark inactive tabs, blue hover states, enlarged navigation/new-tab buttons, native ReyOS Shield icon.

## Known limits / next work

- Shields v1 is not an EasyList/uBlock-compatible blocker. It does not reliably block YouTube ads and has no cosmetic filtering, filter-subscription updater, or persistent per-site rules.

- Verify Reader Mode and Find in Page on several real articles, plus Low Memory Mode tab freeze/discard/reload behavior, then perform real-site, low-memory, multi-tab, video, login, and download-failure tests before ISO inclusion.

## Implementation locations

- Package: `reyos-packages/reyos-browser`
- Application: `files/usr/share/reyos/browser/main.py`
- UI: `files/usr/share/reyos/browser/qml/Main.qml`
- Shields domain list: `files/usr/share/reyos/browser/shields-blocklist.txt`
- Icon: `files/usr/share/reyos/browser/icons/reyos-shields.svg`

## Build and deployment policy

Build on the Dev VM with `makepkg -f --noconfirm`, install there with `pacman -U`, then stage to `/home/reyrubi/reyos-build/local-repo` and add `reyos-browser` to `reyos-iso/packages.x86_64` only after all browser acceptance tests pass. Deploy resulting ISOs only to ReyOS-Test.
