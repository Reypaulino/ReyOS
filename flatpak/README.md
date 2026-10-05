Reyva Flatpak (Flathub)

App ID `com.reyapps.Reyva`, built on `org.kde.Platform//6.11` with the
`io.qt.PySide.BaseApp//6.11` base app, which provides PySide6 and QtWebEngine
built from source (no PyPI binary wheels, as Flathub requires).

Python deps bundled by the manifest:
- `jeepney` (pure-Python wheel) — Secret Service client for saved passwords,
  via `linux_dbus.py`. Replaces `python-secretstorage`, which needs the compiled
  `cryptography` package.
- `setproctitle` (built from sdist) — process name in system monitors.

Sandbox differences from the Arch/.deb builds (`browserBackend.sandboxed`):
- "Install This Site as an App" and "Manage Web Apps" are hidden: the sandbox
  can't write launchers to the host. The proper fix is the
  `org.freedesktop.portal.DynamicLauncher` portal — not built yet.
- "System Password Manager" button is hidden (can't start host apps).
- Notifications go over D-Bus directly (`notify-send` isn't in the runtime).
- State lives in `~/.var/app/com.reyapps.Reyva/data/reyos-browser/`
  (`XDG_DATA_HOME`), not `~/.local/share/reyos-browser/`.

Build and test locally (from this directory) — swap the git source for the
working tree first, since the manifest pins a public commit:

    sed '/- type: git/,$d' com.reyapps.Reyva.yaml > local-test.yaml
    printf '      - type: dir\n        path: ..\n        skip: [flatpak/.flatpak-builder, flatpak/build-dir, flatpak/repo, .git]\n' >> local-test.yaml
    flatpak-builder --user --force-clean --install --disable-rofiles-fuse build-dir local-test.yaml
    flatpak run com.reyapps.Reyva https://example.com

Lint (needs `org.flatpak.Builder` from Flathub):

    flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest com.reyapps.Reyva.yaml
    flatpak build-export repo build-dir
    flatpak run --command=flatpak-builder-lint org.flatpak.Builder repo repo

The repo lint's only errors locally are `appstream-screenshots-not-mirrored-in-ostree`
and `appstream-external-screenshot-url`; Flathub's build pipeline mirrors
screenshots itself. If `build-export` fails with `min-free-space-percent`, the
disk is below OSTree's 3% reserve: `ostree config --repo=repo set core.min-free-space-size 300MB`.

Verified 2026-10-05 on the Ubuntu host: builds, launches, renders the New Tab
page and real sites, opens URLs passed on the command line, saves settings to
the sandboxed data dir, and saves/reads/deletes a password through the host's
Secret Service from inside the sandbox.

Before submitting to Flathub:
- Point the manifest's `commit:` at a public `main` commit containing the files
  it installs (this directory + `reyos-packages/reyos-browser/`).
- Submission = PR to `github.com/flathub/flathub` (branch `new-pr`) with just
  the manifest. After acceptance, Flathub issues a token to place at
  `https://reyapps.com/.well-known/org.flathub.VerifiedApps.txt` for the
  verified-publisher badge.
- Not yet checked in the sandbox: downloads to `~/Downloads`, CSV password
  import and bookmark import through the file-chooser portal.
