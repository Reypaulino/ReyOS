# ReyOS Scan (work in progress — GitHub #21)

Standalone malware scanner (ClamAV) for Ubuntu and ReyOS, sharing one core.

- `reyos_scan/core.py` — distro-neutral core: scans, reports, quarantine, pre-run check with a SHA-256 + definitions cache.
- `reyos_scan/cli.py` — `reyos-scan status|scan|check|run-checked|quarantine|history`.
- `reyos_scan/qt.py` — PySide6 (ReyOS) or PyQt6 (Ubuntu 24.04) bindings.

Tests: `python3 -m unittest discover -s tests -v` (fake ClamAV everywhere; real ClamAV cases when it's installed with definitions). Results and real-machine runs: `docs/ubuntu-scan-testing.md`.

Still to do (in order): `gui.py` (Qt Widgets), `bin/` launchers, `packaging/build-deb.sh`, install and click-through on Ubuntu, then ReyOS's `security_scan.py` as a thin adapter over a copy of `core.py` (kept identical by a test), then a PR. Nothing published until the owner approves.
