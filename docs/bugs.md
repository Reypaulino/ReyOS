# ReyOS — Known Open Bugs

Bugs that are confirmed real but not yet fixed. See `fixes.md` for the ones that *are* resolved.

This file was rewritten from scratch on 2026-08-18 after a full audit of the working tree (most of the source had drifted weeks ahead of the previous version of this doc, which still described things that were already fixed or no longer applied). Anything not carried forward from the previous version was either confirmed resolved (moved to `fixes.md`) or could no longer be confirmed as still true and was dropped rather than carried forward as stale guesswork.

## Control Center renders without icons/wrong theme if launched while the session is locked

Observed directly (2026-08-18): launching `python3 /usr/share/reyos/control-center/main.py` while the KDE session was still at the lock screen produced a window with the correct layout but a generic light Qt style and no sidebar icons at all. A second launch after the session was fully unlocked and settled rendered correctly (Midnight Copper dark theme, all sidebar icons present). Working theory, not rigorously isolated: Qt/Kirigami's icon-theme and platform-style lookup comes back empty if the app starts before Plasma's theming services are fully live (e.g., right at/before unlock), and it silently falls back instead of retrying. Low priority — no normal user workflow launches Control Center from a locked screen — but worth a real isolated repro if it's ever hit organically (e.g. via an autostart entry that races the lock screen on login).

## Bookmarks are the one thing that survives a ReyOS Browser session — and can't be individually removed from the list

`reyos-browser`'s new Bookmarks feature (added since the last documented version) writes to `~/.local/share/reyos-browser/bookmarks.json` on disk (atomic write, `0600`, `0700` parent dir) and survives across sessions — this is a deliberate exception to the browser's private-by-default, nothing-persists design (worth confirming that's an intentional product decision, not scope creep, since it's the only persistent state anywhere in the app). Separately, and definitely a bug: the bookmarks list dialog has an "Open" button per entry but no delete/remove control — the only way to un-bookmark a page is to revisit it and re-click the star toggle, which most users won't discover.

## Welcome wizard sometimes needs a double-click on first launch

Launched via autostart with no window focus — the first click on any button gets consumed by the compositor just to raise/focus the window, never reaching the button underneath. A retry-based `requestActivate()` loop reduced but did not eliminate it. Leading theory: Wayland's activation-token model blocks self-activation for apps launched via a raw systemd/XDG autostart entry with no token-granting launch path, which would make this a platform limitation rather than something fixable purely in app code. Not revisited since first observed.

## Bottom panel isn't reliably "fit content, centered" out of the box

No stored width/alignment key has ever been found in any panel-building path (the old static `panel-template.conf` never had one, and it's since been established that file is dead code anyway — see `fixes.md`; the two live Plasma-scripting panel builders, `reyos-apply-branding.sh` and `reyos-kde-customization`'s script, don't set one either). A real fix needs someone to set "Fit Content" + centered live via Plasma's own Edit Mode UI, then diff the resulting `plasma-org.kde.plasma.desktop-appletsrc` to find the real keys Plasma writes, and add those to whichever script is the actual source of truth. Deprioritized — adjustable via System Settings in the meantime.

## Custom `reyos-*` packages can't be opt-in installed post-boot (architectural gap)

`[reyos-local]` in `packages.x86_64`'s `pacman.conf` points at `file:///home/reyrubi/reyos-build/local-repo`, a path that only exists on the build VM. Baking a `reyos-*` package into the squashfs at ISO-build time works fine, but any `reyos-*` package meant to be offered as an opt-in install *after* boot (e.g. from Welcome's software picker) has no way to resolve on a standalone booted system. No current package needs this (the `reyos-kernel`/`linux-cachyos` case that originally surfaced this was removed entirely), but it'll resurface the next time a custom package needs to be opt-in rather than pre-baked. Not attempted — would need either shipping a self-contained repo subset on the ISO itself, or generating `pacman.conf` at build time with a path that ships with the image.

## GRUB does not reliably auto-boot the default entry

Observed on the Dev VM after the standard-kernel migration reboot: GRUB stayed at the menu with the correct entry pre-selected until a key was sent manually. Not yet root-caused (timeout/default config not yet inspected in the actual `reyos-grub` boot package), and not yet retested since. Don't patch blindly from this single Dev-only observation — reproduce first.

## Desktop Folder Settings dialog shows a stock "About" tab

Right-click desktop → Configure Desktop and Wallpaper opens Folder View's own settings dialog, which always includes a generic plugin "About" tab appended automatically by Plasma's own config-dialog framework — not specific to ReyOS's config, and no kiosk restriction found to suppress it. Purely cosmetic; disproportionate effort to fix (would mean patching Plasma itself). Deprioritized.
