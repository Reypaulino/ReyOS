# ReyOS Scan: what's next (planned, not started)

Agreed with the owner on 2026-10-27: do all of these, after PR #23 (#21: Ubuntu app, shared core, ReyOS adapter) is picked back up and merged. Nothing here is built yet.

What it can't promise: no scanner detects every malicious file. New or custom malware is made to slip past scanners, so the plan pairs better detection (1–3) with limiting the damage (4–5).

## 1. More detection from ClamAV (small)
- Turn on ClamAV's extra checks: `--detect-pua=yes` (adware, bundled junk; maybe "suspicious" rather than "threat"), `--alert-encrypted=yes`, `--alert-broken=yes`, `--alert-macros=yes`.
- Add community signature databases on top of ClamAV's own (e.g. Sanesecurity, URLhaus): check their licences, update them as part of the same update job (ReyOS: `reyos-admin malware-setup`; Ubuntu: alongside freshclam, never a second competing updater), and say in each report which databases were used.
- YARA rules (e.g. YARA Forge's community set), run on Windows programs and installers. Expect some false alarms: report matches as "suspicious", not "threat".

## 2. Inspect Windows programs before they run
For `.exe`/`.dll`/installers in Add PC game and "Check a game installer": flag "suspicious, look closer" (never a hard block) when a program is packed or encrypted (high entropy, UPX and other packer sections), imports APIs typical of malware (process injection, keyboard hooks, hiding itself), or has a missing/invalid Authenticode signature where the publisher normally signs. `python-pefile` is already installed with Lutris on ReyOS; Ubuntu has `python3-pefile`.

## 3. Reputation lookup by fingerprint (opt-in, off by default)
Send only the SHA-256, never the file or its name, to MalwareBazaar (free, no key) and optionally VirusTotal (the user's own free API key). "Known bad elsewhere" → threat; unknown → nothing changes. A switch in the app, explained, off by default (#21: no cloud submission by default). Cache the answers like the scan cache.

## 4. Contain Windows games (the biggest gain)
Run Lutris/umu games inside bubblewrap: the game sees its own prefix and game folder, `/tmp`, the GPU, sound and input, and nothing else in `$HOME` (no documents, SSH keys, browser profiles). Optional per game: no network. This protects against malware nothing knows yet. Needs care with Proton/pressure-vessel (it uses bubblewrap itself), controllers, the NVIDIA card, saves outside the prefix and mods. Test on the laptop with real games (NFS Most Wanted, Prince of Persia) before it's the default; start as a per-game switch.

## 5. "What did it change?" after a game's first run
Snapshot what persistence points look like before the first start, compare after it closes, and warn on anything new: `~/.config/autostart`, systemd user units, shell startup files (`.bashrc`, `.profile`), `~/.ssh`, crontab, browser extension folders, and files written outside the game's prefix and folder.

## Order
4 + 1 first (contain + catch more), then 2, then 3, then 5. Each lands in the shared core where it isn't ReyOS-specific, so the Ubuntu app gets it too.
