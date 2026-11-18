# ReyOS — Known Open Bugs

Bugs that are confirmed real but not yet fixed. Newest first. See `fixes.md` for the ones that *are* resolved.

Started 2026-11-02. Bugs reported before then are in `bugs-old.md` (not re-checked): move one here when it's re-confirmed.

## Reyva .deb (and probably Windows): no H.264/AAC video (2026-11-17)

Owner: AnimeKai (`anikai.org`) videos stopped playing after switching from the Flatpak to the `.deb` (journal: `JW Player Error 102630` on every episode). Checked with `MediaSource.isTypeSupported`/`canPlayType` in a page: the `.deb`'s PySide6 6.x pip QtWebEngine says no to `avc1.*` and `mp4a.40.2`, yes to VP9; the Flatpak (Flathub's QtWebEngine) says yes to all. The Shields list was not the cause (same failure with nothing blocked). Windows uses the same pip wheels: probably the same, not checked. Fixing it needs a QtWebEngine built with `-webengine-proprietary-codecs`. Workaround: use the Flatpak (ReyOS's `reyos-browser` already runs the Flatpak).

## xdg-desktop-portal 1.22.1 (Arch/ReyOS) locked up after a DynamicLauncher icon check (2026-11-17)

Dev VM: the first Install as App of the session left `xdg-desktop-portal` deadlocked (main thread in a futex wait, a `pool-5` worker in a nested main loop since the icon check; every portal call then timed out, so no "Create launcher" dialog and other Flatpak apps' portal calls hang too). `systemctl --user restart xdg-desktop-portal` fixed it; the next installs worked. Not reproduced a second time. Reyva 0.1.14 times out its portal calls and writes the launcher itself instead. Upstream bug, not reported yet.

