# Remote Play: testing (GitHub #22)

What has really been run, where, and what's still **PENDING**. Anything not physically run says PENDING.

## Versions

- Sunshine `2026.914.233613-1` (LizardByte's Arch package, sha256 `17eb8c4d…bba87`, the same as the digest on their release), in `reyos-local` since 2026-10-27 (`reyos-pages` `04fefec`).
- reyos-control-center-gui `1.0.0-146`, reyos-control-center `1.0.0-29`.
- Dev VM: Arch snapshot 2026/10/24 (the install moved it there), Plasma 6.8.0 Wayland, KWin 6.8.0, virtio GPU (no VA-API), 1280×800.
- Client for the VM test: Moonlight-qt 6.2.0 AppImage (sha256 `787b0dcb…92437`) on the Ubuntu 24.04 host, under Xvfb.

## Automated tests

`python3 -m unittest tests.test_remote_play tests.test_pc_games_drives_saves` (no Sunshine needed): Sunshine config merge (forced vs default keys, comments, no rewrite when unchanged), Moonlight app list (ReyOS Games added after Desktop, Sunshine's xrandr sample dropped, user entries kept, old test command repaired), `vainfo` parsing (Intel encode vs decode-only), NVIDIA render node skipped for VA-API, Sunshine log parsing (encoder in use, failed encoders, software flag), home-network addresses (VPN and VM bridges skipped), Tailscale direct/relayed/signed out/not installed, pairing input checks (nothing reaches Sunshine with a bad id/PIN/uuid), firewall rules (private ranges and `tailscale0` only, never 47990, "on" needs the password). **2026-10-27: all passing.**

## Dev VM (2026-10-27): done

| Step | Result |
|---|---|
| Control Center → Gaming → Remote Play → Install | ✅ installed `sunshine` + `libva-utils` from the signed `reyos-local` through `reyos-channel install` (one transaction with the waiting snapshot move to 2026/10/24). No `intel-media-driver` (no Intel GPU in the VM): correct. |
| Files written | ✅ `sunshine.conf`: `origin_web_ui_allowed = pc`, `upnp = disabled`, `max_bitrate = 15000`, `capture = kwin` (no `encoder`: no VA-API encoder on virtio). `apps.json`: Desktop, ReyOS Games (with a generated 600×800 cover), Steam Big Picture. `remote-play.json` mode 600. |
| Turn on | ✅ KWin capture of Virtual-1 1280×800; encoder `libx264 [software]` (NVENC, VA-API, Vulkan fail on virtio, as expected). The panel shows the CPU-encoding warning. Web settings only on 47990 with `pc` origin. |
| Firewall → Allow (password prompt) | ✅ polkit prompt; 13 ufw rules with comment "ReyOS Remote Play" (TCP 47984,47989,48010 + UDP 47998:48000,48002 + mDNS 5353 from 192.168/16, 10/8, 172.16/12; TCP/UDP on `tailscale0`). 47990 not opened. |
| Pairing from a real Moonlight client | ✅ `moonlight pair 192.168.122.19 --pin 4821` on the host: "roth (192.168.122.1) wants to stream from this PC" appeared in Control Center; PIN typed, Pair → "roth is paired"; Moonlight's pairing finished. |
| Moonlight's app list | ✅ `moonlight list`: Desktop, ReyOS Games, Steam Big Picture. |
| ReyOS Games → Play on another device… | ✅ toolbar button shows (installed + switch on); the window shows status, paired device "roth", help and buttons. "Don't show this here" hides the button and turns the Control Center switch off; the switch turns it back on. |
| Copy diagnostics | ✅ report on the clipboard (versions, session, settings, GPU/VA-API, encoder, addresses, Tailscale, ports, last errors); no password. |
| Start at login + reboot | ✅ after a real reboot and login, Sunshine started by itself with KWin capture. |
| Turn off | ✅ service stopped, nothing listening on 47984/47989/47990/48010. |
| Block again (no password) | ✅ all 13 rules removed. |

Bugs found and fixed during this test (not in any published build): ReyOS Games' entry in Moonlight pointed at a `reyos-games` command that doesn't exist (now the real `games.py` path, and an entry written with the old command is repaired); the install progress line was hidden; the firewall warning's button covered its text; the ReyOS Games window had a zero-height panel (the help text's natural width broke the dialog's layout); a binding warning when Tailscale isn't installed; the panel didn't refresh when the window came back to the front.

**Owner's iPhone → Dev VM, 2026-10-27 (real stream):** iPhone Moonlight paired as "iphone test" through Control Center's PIN box (address 192.168.68.87, the VM's home-network NIC) and streamed Desktop twice (10:23–10:25, 10:25–). Sunshine on the VM: KWin capture 1280×800, libx264 software encode, ~6 Mbps sent, 80–84 % of one core for Sunshine; VM load ~6.5 on 5 cores (KWin software rendering ~1.3 cores, RetroArch, Sunshine). The iPhone showed "slow connection, reduce the bitrate": the VM's CPU, not the network (no send errors on the NIC). Virtual keyboard, mouse, touchscreen and pen created; audio moved to Sunshine's sink during the stream and back after. The owner's N64-style controller (paired to the iPhone) arrived as "Sunshine (libvirtualhid) X-Box Series Controller" (045e:0b13; 16 buttons, 6 axes, D-pad as hat); ReyOS lists it as an Xbox pad but had no RetroArch profile for it, so N64 games ignored it until the owner ran ReyOS Games → Controller… while streaming; then it worked. Two RetroArch processes were running during the stream (cause not checked: the owner may have started the game twice).

Follow-up: ship RetroArch profiles for Sunshine's virtual pads (Xbox Series, DualShock 4, DualSense, Switch) so a streamed controller works without setup. That needs a full-size controller run through every button (the N64 pad's profile has no right/top face button, right trigger or Select).

**Not done from the host:** a video stream to Moonlight on the Ubuntu host. Running Moonlight's `stream` was blocked by this session's command checks, so streaming, audio, and input over a stream have **not** been run anywhere yet.

## Real hardware (owner, 2026-10-27): PENDING

Laptop: ThinkPad T470p, Intel HD 630 + GeForce 940MX (GM108, NVIDIA 580), ReyOS Plasma Wayland. Write results here with model/OS/app versions; redact nothing private from the diagnostics except what you don't want public.

- [ ] **A. Install + pair (LAN).** Update everything → Gaming → Remote Play → Install → Turn on → Allow. Moonlight on the Apple TV 4K: pair (PIN in Control Center). Stream **Desktop**, then **ReyOS Games** → NFS Most Wanted (Lutris/Proton), a PS2 game (PCSX2), a Steam game. PENDING
- [ ] **B. Quality.** 720p60 ~8 Mbps H.264; then 1080p60 ~12 Mbps. Note latency (Moonlight's stats overlay: Ctrl+Alt+Shift+S on a PC client; long-press on Apple TV), frame drops, audio, every controller button, reconnect after closing Moonlight, and what happens after the laptop sleeps. PENDING
- [ ] **C. iPhone.** Same Wi-Fi; then cellular + Tailscale (sign in on the laptop in Connect → VPN and on the iPhone; add the 100.x address in Moonlight). Note whether the panel says the iPhone is **direct** or **relayed**. PENDING
- [ ] **D. Encoder.** Copy diagnostics after Turn on: expected `encoder = vaapi`, `adapter_name` = the Intel render node, "H.264 with h264_vaapi". Run a game on the NVIDIA card (Graphics card for games = NVIDIA) while streaming: stable? PENDING
- [ ] **E. Security.** An unpaired device can't stream; Remove a paired device and check it has to pair again; `https://<laptop-ip>:47990` from another device doesn't open; Turn off ends a running stream; Block again closes the ports. PENDING
- [ ] **F.** Paste the diagnostics and results into this file. PENDING

Release acceptance (from #22): paired Apple TV streams one game with audio and controller over LAN; iPhone streams on local Wi-Fi; the Tailscale path works when available; no regression in existing games. **Not met yet: all real-hardware items are PENDING.**
