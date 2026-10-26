# ReyOS Scan (work in progress — GitHub #21)

Standalone malware scanner (ClamAV) for Ubuntu and ReyOS, sharing one core.

- `reyos_scan/core.py` — distro-neutral core: scans, reports, quarantine, pre-run check with a SHA-256 + definitions cache.
- `reyos_scan/cli.py` — `reyos-scan status|scan|check|run-checked|quarantine|history`.
- `reyos_scan/qt.py` — PySide6 (ReyOS) or PyQt6 (Ubuntu 24.04) bindings.

Still to do (in order): `gui.py` (Qt Widgets), `bin/` launchers, `packaging/build-deb.sh`, `tests/`, `docs/ubuntu-scan-testing.md`, real-Ubuntu tests on the owner's laptop, then ReyOS's `security_scan.py` as a thin adapter over a copy of `core.py` (kept identical by a test), then a PR. Nothing published until the owner approves.
