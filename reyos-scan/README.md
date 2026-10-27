# ReyOS Scan (GitHub #21)

On-demand malware scanner (ClamAV) for Ubuntu and ReyOS, sharing one core. It runs as you, only when asked (no background scanner); ClamAV's own updater keeps the definitions current.

- `reyos_scan/core.py`: distro-neutral core. Scans, reports, quarantine, the pre-run check for game installers (SHA-256 + definitions cache), one scan at a time, disc images left out of Quick scan and listed apart. ReyOS Control Center uses an identical copy (`reyos_scan_core.py`, checked by `tests/test_core.py`) behind its `security_scan.py` adapter.
- `reyos_scan/cli.py`: `reyos-scan status | scan --quick|--home|PATH… | check FILE | run-checked FILE -- CMD… | quarantine … | history`.
- `reyos_scan/gui.py`: the window (Qt Widgets; PySide6 on ReyOS, PyQt6 on Ubuntu 24.04 via `qt.py`).

## Ubuntu package

```
packaging/build-deb.sh            # -> dist/reyos-scan_0.1.0_all.deb (dpkg-deb only; same input = same file)
sudo apt install ./dist/reyos-scan_0.1.0_all.deb
```

Depends on `python3`, `python3-pyqt6` (or `python3-pyside6`), `clamav`, `clamav-freshclam`. It installs `reyos-scan` and `reyos-scan-gui` in `/usr/bin`, the code in `/usr/lib/reyos-scan`, a "ReyOS Scan" launcher and icon. `sudo apt remove reyos-scan` removes all of that; your reports and quarantine stay in `~/.local/share/reyos/security`.

Definitions: Ubuntu's `clamav-freshclam` service updates them. If it's off, the app says so; turn it on with `sudo systemctl enable --now clamav-freshclam`. ReyOS Scan never runs its own updater next to it.

## Before running a Windows game (Lutris)

"Check a game installer…" in the window, or `reyos-scan check game.exe` on the command line, checks the .exe and the programs, DLLs and archives next to it. Unchanged files that were already found clean with the same definitions aren't scanned again.

To check before every start, set the game's Lutris **System options → Command prefix** to `reyos-scan run-checked /path/to/game.exe --`. The game then only starts when the check is clean. ReyOS Scan never changes Lutris settings by itself. A clean result means "no known threats", not "safe": Wine and Proton don't sandbox Windows programs.

## Tests

```
python3 -m unittest discover -s tests -v                                      # fake ClamAV everywhere; real ClamAV cases when installed
QT_QPA_PLATFORM=offscreen python3 tests/gui_smoke.py                          # the window, offscreen, with real ClamAV
REYOS_SCAN_LIB=/usr/lib/reyos-scan QT_QPA_PLATFORM=offscreen python3 tests/gui_smoke.py   # same, against the installed .deb
```

Results and real-machine runs: `docs/ubuntu-scan-testing.md`.
