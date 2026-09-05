# ReyOS package repository

This branch hosts the `reyos-local` pacman repository via GitHub Pages —
the `reyos-*` packages that make up ReyOS's own branding and tooling.

Not meant to be browsed directly. On an installed ReyOS system, this is
configured in `/etc/pacman.conf` as:

```
[reyos-local]
SigLevel = Optional TrustAll
Server = https://reypaulino.github.io/ReyOS/
```

This branch is regenerated wholesale from the dev build's `local-repo` —
don't hand-edit it here.
