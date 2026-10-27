# ReyOS Scan on Ubuntu: testing (GitHub #21)

What has really been run, where, and what's still PENDING. Anything not physically run says PENDING.

## Test machine

ThinkPad T470p, Ubuntu 24.04.5 (nvme0n1p2): i7-7820HQ (4 cores / 8 threads), 32 GB RAM, Python 3.12.
ClamAV 1.5.4 from Ubuntu (`apt install clamav clamav-freshclam`, 2026-10-26). `clamav-freshclam.service` started by itself and downloaded the definitions (daily 28165, main 63, bytecode 339; 108 MB in `/var/lib/clamav`) in about 2 minutes.

## Automated tests

```
cd reyos-scan
python3 -m unittest discover -s tests -v                      # all
REYOS_SCAN_SLOW=1 python3 -m unittest discover -s tests -v    # + 450 MB archive (~1.5 min)
```

- `tests/test_core.py` runs anywhere: it uses `tests/fake-clamscan` and a temporary HOME, so it covers output parsing, statuses, the pre-run cache, quarantine and CLI exit codes without ClamAV. It also checks that ReyOS's copy of `core.py` is identical (skipped until the ReyOS adapter exists).
- `tests/test_real.py` runs against the real ClamAV and its definitions, and skips itself without them. Each scan spends about 11 s loading the definitions.

**Result on the T470p, 2026-10-26: 41 tests, all passing (1 skipped: the ReyOS copy).** Wall time 195 s; peak RSS 1.1 GB, which is clamscan with the definitions loaded.

| Real case | Result | Time |
|---|---|---|
| Clean folder (text file, zip) | clean | 11.5 s |
| EICAR as .com, .exe, .dll and inside a .zip | found, 4 of 4 | 11.3 s |
| Symlink loop, link to `/`, link to a folder with EICAR | clean, 0 files: links not followed | 11.4 s |
| Unreadable file (mode 000) | not verified, "Access denied" | 11.3 s |
| Zip nested 20 levels deep | not verified (MaxRecursion) | 11.5 s |
| Zip bomb over the limits (scaled to 40M) | not verified (MaxScanSize) | 11.9 s |
| Archive member over the file limit, any-offset signature | 30M member found; 100M member not verified | <1 s (own signature db) |
| 450 MB of zeros in a 0.5 MB zip (under the real limits) | clean, fully unpacked | 94.8 s |
| Cancel mid-scan | cancelled, stops within seconds | — |
| Game check: .exe plus a .dll holding EICAR → quarantine → recheck → restore | found; then clean; second check uses the cache (1 unchanged); restore matches SHA-256 | — |

## Bugs the real runs found (fixed in core)

1. **Archive members over `--max-filesize` were skipped silently.** ClamAV 1.5.4 skips a file *inside an archive* that's bigger than `--max-filesize` with no alert, even with `--alert-exceeds-max=yes`, and reports the archive OK. With the old limits (500M file / 1000M scan), anything in a 500M–1000M member would have come back "clean". It's checked with a custom any-offset signature, since EICAR only matches at the start of a file. Fix: `--max-filesize` = `--max-scansize` = 500M, so ClamAV raises MaxScanSize instead, plus a test that keeps them that way. **ReyOS Scan v1 (Control Center 143) has the same gap**: it passes no limits, so ClamAV's defaults apply (100M / 400M, no alert). The ReyOS adapter fixes it.
2. **"Access denied" wasn't recorded as an error.** clamscan prints `path: Access denied` with no `ERROR` suffix. The status was still "not verified" (exit code 2), but the report didn't name the file. Every other `path: message` line now counts as a problem, except OK, Empty file, Symbolic link and Excluded. v1 has the same gap.
3. **`path: Virus(es) detected ERROR`** follows every detection, limit alerts included, so it was being counted as a read error. It's now ignored.
4. The scanner's output pipe was never closed (a ResourceWarning).

## Known ClamAV limitation (not fixable in ReyOS Scan)

A zip entry written with a zip64 local header and a data descriptor (Python's `ZipFile.open(name, "w", force_zip64=True)`) is reported **OK without being unpacked**: EICAR inside it isn't detected. The same EICAR in a normal or plain-streamed zip is found. ClamAV's debug log says `local header - stream out of file … Skipping decompression`. This is worth reporting upstream; ReyOS Scan can't see it from clamscan's output.

## Cost of the limits

The limits now mean 500 MB unpacked per file or archive. A highly compressible archive just under that (450 MB of zeros in 0.5 MB) costs about 95 s of CPU on this machine (600 MB took about 1m45). Bigger archives, ISOs and multi-GB game archives are reported "not checked", never "clean".

## Real quick scan

`reyos-scan scan --quick` (the CLI from the source tree, with a temporary data folder) over the owner's real `~/Downloads` (6.4 GB) and `~/Desktop` (6.0 GB), 2026-10-26:

- Result: **not verified**. 41,404 files checked, no threats; 7 files "not checked" (MaxFileSize): PS2/PSP disc images (.iso/.chd), a 7z ROM archive and two big Need for Speed data files. Exit code 2.
- Time: **36 min 46 s** wall, 2027 s user CPU (clamscan is single-threaded: one core at 99%). Peak RSS 1.2 GB.
- `reyos-scan status` afterwards showed the definitions, "updates automatically (clamav-freshclam service)" and the last scan.

What this shows: when Downloads/Desktop hold game folders and disc images, a "quick" scan isn't quick, and big ROMs and ISOs always keep it from reading "no known threats". To decide with the owner: say up front how much is about to be scanned, and maybe leave disc images (.iso/.chd/.cso) out of Quick scan or show them apart from real problems.

## 2026-10-27: window app, .deb and ReyOS adapter

Ubuntu 24.04.5 LTS (the T470p), ClamAV 1.5.4, definitions 28165.

- **Core additions**, with tests: only one scan at a time (a lock in the data folder: a second scan is refused with "Another ReyOS Scan is running", never run alongside, since each clamscan holds about 1 GB); Quick scan leaves disc images out (.iso .chd .cso .img .rvz .wbfs, matched case-insensitively) and lists them apart, so they no longer make every quick scan "not verified" (the owner's question from 10-26; decided this way pending the owner's OK). Two real bugs fixed while testing on ReyOS: a pre-run check whose files all came from the cache saved its report with the placeholder summary ("Nothing new to check."), and two reports saved in the same second sorted the wrong way, so "last scan" showed the older one. Report names now carry milliseconds.
- **Unit tests:** 44, all passing on this machine with real ClamAV (2 skipped: the optional 450 MB archive test, and the ReyOS-copy check runs in the repo checkout). 2 min 23 s wall, peak RSS 1.1 GB.
- **.deb:** `packaging/build-deb.sh` → `reyos-scan_0.1.0_all.deb` (16 KB). Built twice → same SHA-256 (reproducible). `sudo apt install ./…deb` pulled `python3-pyqt6` and installed cleanly; `reyos-scan status` worked from `/usr/bin`; `desktop-file-validate` OK; `apt remove` left none of its files; reinstalled.
- **GUI smoke test** (`tests/gui_smoke.py`, offscreen, real ClamAV, against both the source tree and the installed .deb): Quick scan with Cancel shown, a second scan refused meanwhile, EICAR found, the disc image listed apart, finding row + Move to quarantine, quarantine then restore with identical bytes, History row, a clean single file, Cancel → "cancelled". All passed. Screenshots checked by eye.
- **Found on this machine:** `clamav-freshclam.service` is now **disabled** (it was running on 10-26; not changed by this work). The app says so and gives `sudo systemctl enable --now clamav-freshclam`. Left as it is for the owner to decide.

## ReyOS (Dev VM, 2026-10-27)

control-center-gui 1.0.0-147 built from this branch (not published), ClamAV 1.5.4, definitions 28166:
- `security_scan.py` is now an adapter over `reyos_scan_core.py` (identical to `core.py`, checked by the test); same data folder, so v1's report and quarantine are still listed.
- Backend with real ClamAV: quick-type scan found EICAR and left a .chd out; Add PC game's check (now `check_program`) took 20.6 s the first time and 0.0 s the second (cache), and caught a DLL replaced by EICAR afterwards; quarantine + restore matched.
- Control Center → Security, clicked: Quick scan over Downloads/Desktop/~/Games showed the EICAR threat with Move to quarantine, "Not checked: Pokemon - SoulSilver Version (USA).zip" (over the limits; v1 would have counted it clean without saying so) and "Left out (disc images): test-disc.iso"; Move to quarantine moved the file (SHA-256 275a021bbfb6…, EICAR's).

## PENDING (not run yet)

- The owner clicking through the installed window on the Ubuntu desktop (it shows in the app grid as "ReyOS Scan").
- External drives (the owner, physically): a USB stick formatted NTFS and one formatted exFAT, mounted by GNOME under `/media/$USER/`; External drive…; unplugging a drive mid-scan (expected: not verified or cancelled, never clean, no crash).
- A full home scan on this machine (time, CPU, RAM).
- ReyOS on the laptop (HD 630 / 940MX): Add PC game with a real installer (check before it runs, cache on a second add), ReyOS Games right-click Scan for viruses, Security → Quick scan with the SD card's game folder, Steam/Lutris/PCSX2 unaffected.
- Publishing: nothing is published. The ReyOS side ships as control-center-gui 147 only after the owner approves.
