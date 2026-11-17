# Reyva 0.1.13 — release notes

Released 2026-11-16 (owner approved). Status of every item: `docs/reyva-audit.md`.

## New

- **New Tab dashboard.** Type on the New Tab page to find an open tab, a
  bookmark or an installed web app; Up/Down and Enter pick one. Open tabs
  switch to the tab you already have (a sleeping tab isn't woken until you
  pick it), web apps open in their own window with their own sign-in, and
  Enter on plain text searches the web with only what you typed. The All /
  Open tabs / Bookmarks / Web apps chips list one kind without typing.
- **Search open tabs** from anywhere with Ctrl+Shift+A (or the search button
  next to New Tab).
- **Tabs on the side** (Settings > Tabs): a vertical tab list instead of the
  strip on top. Off by default.
- **Guided welcome tour** on a brand-new profile: each step lights up the
  part of the window it explains (New Tab search, address bar, tabs, Shields,
  Web Apps, menu), with bookmark import (and how to export them from
  Chrome/Edge/Brave/Opera, Firefox and Safari), optional password import
  (with a warning that a password CSV isn't encrypted) and the search engine
  inside the steps. Skippable; never shown on an upgrade or
  when Reyva was opened with a link. Settings > Welcome tour shows it again.
- **Restore tabs after a crash** (Settings > Tabs, **off by default**). When
  on, only the addresses and titles of your open tabs are kept in a private
  file while Reyva runs; a normal quit deletes it. After a crash Reyva asks
  whether to reopen them.
- **Privacy & Shields** shows how many requests were blocked on the current
  site, the filter list's size and date with an Update button, and the
  permissions you gave the site this session, each with Reset. Turning
  Shields off for a site now reloads it, so the change is visible at once.
- **Web Apps button** in the toolbar: all your installed web apps as tiles,
  one click opens one. **Install as App** button at the end of the address
  bar. Web Apps list: **Open** button next to Remove.
- Side tabs fold down to a strip of site icons.

## Fixed

- **Pages loaded very slowly after updating the Shields filter list.** Every
  request was checked against all ~150,000 domains one by one (about 43 ms
  per request); a page with 80 images took over 4 s longer. Now a lookup per
  parent domain (about 1 µs).
- **Routers, printers, NAS boxes and local servers wouldn't open.** Every
  http:// address was switched to https:// with no way back. Local addresses,
  IP addresses and one-word names are no longer switched; when an internet
  site has no working HTTPS, Reyva says so and offers to open it over HTTP for
  that session.
- **Site permission requests were never answered.** Block and closing the
  dialog called a method that doesn't exist in Qt 6.8+, so the site waited
  forever. The dialog now names the site that asked (not the tab you were
  looking at) and what it wants, and several requests wait their turn.
- **Installed web apps (Ubuntu .deb): a title with " or $ gave a launcher
  that didn't start, and an address with %20 opened the wrong page.** The
  launcher now follows the desktop-entry escaping rules.
- "What's new" and "Report a problem" in Settings opened a tab in the
  background, so nothing seemed to happen.
- The menu was cut off at the bottom in a normal-size window; the reload
  icon was off-center; Install as App and Manage Web Apps looked unfinished
  (cut-off addresses); dialogs now dim the page behind them.

## Under the hood

- The Web Apps list is read once and cached instead of on every redraw
  (on the Flatpak that was one D-Bus call per app each time).
- Logic that needs no Qt lives in `reyva_core.py`, with unit tests.
