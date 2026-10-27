# Remote Play (Sunshine + Moonlight)

Play a ReyOS PC's games on an Apple TV, iPhone, iPad, Android device or another PC. The game runs on the ReyOS PC; [Sunshine](https://github.com/LizardByte/Sunshine) streams the screen and sound, and the free **Moonlight** app on the other device shows it and sends the controller back.

It's **optional and off by default**: nothing is installed, started at login or let through the firewall until you say so.

Where it is:

- **Control Center → Gaming → Setup → Remote Play (TV, phone, tablet)**: install, turn on/off, start at login, firewall, pairing, paired devices, diagnostics, and a switch for ReyOS Games.
- **ReyOS Games → Play on another device…**: the same panel in a window. The button only shows when Remote Play is installed and its switch is on. "Don't show this here" in that window hides it again.

## Installing

Control Center → Gaming → Remote Play → **Install Remote Play**. It installs through the normal update channel (one transaction with any waiting updates, no partial upgrades):

- `sunshine`: LizardByte's official Arch package, unchanged, signed into ReyOS's own repo (`reyos-local`).
- `libva-utils` (`vainfo`, to check the video encoder).
- `intel-media-driver` on PCs with Intel graphics (the H.264/HEVC encoder on most laptops).

Sunshine's package adds a udev rule that gives the logged-in user `/dev/uinput` and `/dev/uhid` (the virtual mouse, keyboard and controllers). No `chmod`, and no `input` group is needed. If the panel says to restart, do it once after the install.

## What ReyOS sets in Sunshine

Written into `~/.config/sunshine/sunshine.conf` on install and at every **Turn on**. Other lines are left alone.

| Setting | Value | Why |
|---|---|---|
| `origin_web_ui_allowed` | `pc` (always) | Sunshine's own web settings only answer on this PC, never from the network. |
| `upnp` | `disabled` (always) | No ports are opened on the router. |
| `max_bitrate` | `15000` (if not set) | 15 Mbps is plenty for 720p/1080p and keeps an older PC's encoder comfortable. |
| `capture` | `kwin` (Plasma Wayland, if not set) | KWin's own screen capture: no extra privileges, survives KWin's overlays. |
| `encoder` / `adapter_name` | `vaapi` + the Intel/AMD render node (if not set and VA-API can encode H.264 there) | Sunshine tries NVENC and Vulkan first; a laptop's GeForce MX/9x0M often has no NVENC (the 940MX/GM108 has none), so the Intel chip encodes while the game can still run on the NVIDIA card. |

A login for Sunshine's web settings is created too: user `reyos`, a random password kept in `~/.config/reyos/remote-play.json` (mode 600). Control Center uses it to list pairing requests. **Copy password** puts it on the clipboard for **Sunshine settings**.

Moonlight's app list gets **ReyOS Games** (next to Desktop). Sunshine's sample "Low Res Desktop" is removed, because it runs `xrandr`, which does nothing on Wayland.

## Firewall

ufw blocks everything coming in by default, so Moonlight can't reach the PC until you press **Allow** (it asks for your password). That adds `reyos-admin remote-play-firewall on`, with the comment "ReyOS Remote Play":

- TCP 47984, 47989, 48010 and UDP 47998–48000, 48002, **only from** 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12 (home networks), plus UDP 5353 (mDNS, so Moonlight finds the PC by itself).
- The same TCP/UDP ports on the `tailscale0` interface (Tailscale devices).
- Never 47990 (the web settings), never the whole internet.

**Block again** removes exactly those rules (no password needed to close).

## Pairing (Apple TV, iPhone, iPad)

1. Install **Moonlight** from the App Store on the Apple TV/iPhone, on the same Wi-Fi as the PC.
2. On the PC, Remote Play must be **On** with the firewall **allowed**.
3. In Moonlight, pick the PC (or press + and type the address the panel shows). Moonlight shows a 4-digit PIN.
4. The request appears in the panel ("Apple TV (192.168.x.x) wants to stream from this PC"). Type the PIN, keep or change the name, press **Pair**. Or **Decline** it.
5. In Moonlight pick **Desktop** or **ReyOS Games**.

Only paired devices can stream. **Paired devices → Remove** unpairs one. A paired device can control the PC's mouse and keyboard while streaming, so only pair your own devices.

**Controller:** pair it with the Apple TV or iPhone (their Bluetooth settings), not with the PC. Moonlight sends it to Sunshine, which creates a virtual Xbox/PlayStation pad on the PC; ReyOS's controller settings and RetroArch's autoconfig aren't changed.

**Picture (Moonlight settings):** start at 720p60, about 8 Mbps, H.264. Try 1080p60 at about 12 Mbps after that. Don't expect 4K from a laptop's encoder, even though the Apple TV can show 4K.

## Away from home (Tailscale)

No router ports, and nothing changes on a T-Mobile style CGNAT connection:

1. On the PC: ReyOS Connect → VPN → set up and sign in to Tailscale.
2. On the iPhone: the Tailscale app, signed in to the same account.
3. In Moonlight on the iPhone, press + and type the PC's Tailscale address (the panel shows it once Tailscale is running).

The panel lists Tailscale devices that are online and whether each one is **direct** or **relayed** (through Tailscale's servers, much slower). If it's relayed, streaming will stutter. No exit node or subnet router is needed.

## Known limits

- **The PC has to be logged in and unlocked.** On Wayland the capture runs inside your desktop session. Use Users → "Automatically log in" if the PC should be reachable after a restart. A locked screen streams the lock screen.
- **Lid closed / screen off:** KWin stops drawing that screen, so there's nothing to capture. Keep the lid open or connect an external display.
- **No video encoder:** without VA-API (or NVENC) H.264 encode, Sunshine encodes on the CPU (`libx264`). The panel warns about it. Use 720p and 30–60 FPS.
- **NVIDIA 580 legacy (Maxwell/Pascal):** many of these laptop chips have no NVENC at all. The game can run on the NVIDIA card while the Intel chip encodes (that's the default ReyOS sets).
- **Sunshine runs as a user service** (`app-dev.lizardbyte.app.Sunshine.service`), so its file capabilities don't apply and KMS capture isn't available. KWin capture doesn't need them. The log's "Failed to gain CAP_SYS_ADMIN" lines are expected.
- Sunshine updates come from ReyOS's repo, so they arrive after ReyOS republishes them, not straight from upstream.

## Troubleshooting

- **Copy diagnostics** puts a report on the clipboard: versions, session, settings, each GPU's VA-API encoders, the encoder Sunshine picked, addresses, Tailscale paths, ports listening, and the last warnings/errors in `~/.config/sunshine/sunshine.log`. The password is never included.
- Moonlight doesn't see the PC: Remote Play on? Firewall allowed? Same Wi-Fi (not a guest network)? Try typing the address.
- Moonlight shows a black screen: the session is locked or the screen is off.
- Buttons do nothing: restart once after installing (udev rule), then check the diagnostics line for `/dev/uinput`.
- "Sunshine didn't accept ReyOS's login": turn Remote Play off and on again (it makes a new login).
- Logs: `~/.config/sunshine/sunshine.log`, `journalctl --user -u app-dev.lizardbyte.app.Sunshine`.

Source: `remote_play.py` (Qt-free), `remote_play_backend.py`, `qml/RemotePlayPanel.qml` in `reyos-control-center-gui`; `remote-play-firewall` in `reyos-admin`. Tests: `tests/test_remote_play.py`. Test log: `docs/remote-play-testing.md`.
