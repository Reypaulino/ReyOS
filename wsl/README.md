# ReyOS WSL — build tree

Full architecture, compatibility classification, and testing status live in
[`docs/wsl.md`](../docs/wsl.md). This file is just the directory map.

```
wsl/
├── build.sh                  run as root on the ReyOS Dev VM — produces
│                              ReyOS-WSL-<version>-x86_64.wsl
├── wsl.conf                  shipped as /etc/wsl.conf
├── rootfs/                   overlay copied verbatim onto the built rootfs
│   ├── etc/os-release
│   └── etc/profile.d/        banner + first-run trigger
├── first-run/
│   └── reyos-wsl-init.sh     installed as /usr/local/bin/reyos-wsl-init
└── package-lists/
    ├── minimal.txt           baked into the shipped artifact
    ├── developer.txt         installed by first-run if chosen
    └── reyos-developer.txt   installed by first-run if chosen
```

`reyos-dev-test` (installed to `/usr/local/bin` inside the image) is the
package build/test helper — see `docs/wsl.md` "ReyOS package testing".

Build:

```
sudo ./build.sh            # must run on the ReyOS Dev VM (Arch/CachyOS host)
```

Do not run `build.sh` anywhere else — it reuses the host's live
`/etc/pacman.conf`, keyring, and mirrorlists on purpose.
