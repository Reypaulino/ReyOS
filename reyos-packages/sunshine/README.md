# sunshine (republished, not built here)

Remote Play (Control Center → Gaming, ReyOS Games) installs Sunshine from `reyos-local`. ReyOS doesn't build it: the file in `reyos-pages` is LizardByte's own Arch package, byte for byte, signed with the ReyOS package key so `SigLevel = Required` accepts it.

| Version | Upstream file | sha256 |
|---|---|---|
| 2026.914.233613-1 | https://github.com/LizardByte/Sunshine/releases/download/v2026.914.233613/sunshine-2026.914.233613-1-x86_64.pkg.tar.zst | `17eb8c4d823a2693038f40aeeab56943ef0d5d6ace8ac90b3693905b0acbba87` (matches the digest on the release) |

To update it: download the new release's `sunshine-*-x86_64.pkg.tar.zst`, compare its sha256 with the digest GitHub shows for the asset, check `ldd` on the binary against the current stable snapshot (the Dev VM: extract it and `ldd usr/bin/sunshine | grep "not found"`), then sign, `repo-add` and publish it like any ReyOS package (`docs/DEVELOPER.md`). Add a row above. Source code: https://github.com/LizardByte/Sunshine (GPL-3.0).
