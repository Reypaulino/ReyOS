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

Single-file bundle for GitHub Releases (what's actually shipped today, since Flathub
is blocked — see below). Builds straight from the manifest's pinned public commit:

    flatpak-builder --user --force-clean --disable-rofiles-fuse --install-deps-from=flathub --repo=repo build-dir com.reyapps.Reyva.yaml
    flatpak build-bundle --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo repo Reyva.flatpak com.reyapps.Reyva

`--runtime-repo` lets the user's `flatpak install` fetch the KDE runtime + PySide
BaseApp from Flathub. Users must download the file first — `flatpak install <https url>`
fails with "Remote bundles are not supported". Release tag pattern:
`reyva-flatpak-v<version>` (not marked Latest — that stays on the ISO). Bump
`<releases>` in the metainfo for each new bundle; no auto-updates yet (would need an
OSTree repo, e.g. on GitHub Pages, plus a `.flatpakref`).

Auto-updating repo (built 2026-10-05, not yet public): a signed static OSTree repo
on GitHub Pages, so `flatpak update`/Discover pick up new versions.

    K=9A17D49EE3929AC6402337FA66E4085621026272
    flatpak-builder --user --force-clean --disable-rofiles-fuse --install-deps-from=flathub --default-branch=stable build-dir com.reyapps.Reyva.yaml
    flatpak build-export --gpg-sign=$K site/repo build-dir stable     # site/repo = `ostree init --mode=archive-z2` once
    flatpak build-update-repo --title=Reyva --default-branch=stable --gpg-sign=$K site/repo

`site/` also holds `com.reyapps.Reyva.flatpakref` (Url, Branch=stable, `RuntimeRepo`
= Flathub, base64 `GPGKey`), `reyva.flatpakrepo`, `reyva.gpg`, `index.html`, `.nojekyll`.
Largest object is ~88 MB (QtWebEngine), close to GitHub's 100 MB per-file limit.
To test without publishing, serve `site/` with `python3 -m http.server` and use a
copy of the flatpakref with a local Url.

**Flathub's generative-AI policy (checked 2026-10-05) blocks an agent-driven submission:**
"Flathub manifests must not contain AI-generated or AI-assisted content", "AI tools or
agents must not open or automate Flathub submission pull requests, or generate their
commit messages, descriptions, review comments, or replies", and AI-generated
application code must be disclosed (parts + extent; reviewers may reject on that basis).
So the manifest here is a working reference only: the submitted manifest has to be
written by a human, and the PR opened and handled by the user. Flathub also wants a
tagged stable release as the source (not a bare commit).

Before submitting to Flathub:
- Point the manifest's `commit:` at a public `main` commit containing the files
  it installs (this directory + `reyos-packages/reyos-browser/`).
- Submission = PR to `github.com/flathub/flathub` (branch `new-pr`) with just
  the manifest. After acceptance, Flathub issues a token to place at
  `https://reyapps.com/.well-known/org.flathub.VerifiedApps.txt` for the
  verified-publisher badge.
- Verified in the sandbox too: downloads land in `~/Downloads`; CSV import goes
  through the file-chooser portal (any folder). Bookmark import uses the same dialog.
