"""ReyOS Scan in Control Center (Security) and ReyOS Games: a thin adapter
over reyos_scan_core.py, which is reyos-scan/reyos_scan/core.py copied
unchanged (reyos-scan/tests/test_core.py checks the two are identical). The
same core is the standalone Ubuntu app; only what's ReyOS's own lives here:
the package to install and the game folders Quick scan includes.

Reports and the quarantine stay where v1 kept them
(~/.local/share/reyos/security), so earlier scans and quarantined files are
still listed."""
import emulation
import reyos_scan_core as core
from reyos_scan_core import (  # noqa: F401  (used by main.py and games.py)
    check_program, definitions, delete, history, installed, last_report, quarantine, quarantined, restore,
    sha256)

PACKAGES = ["clamav"]


def quick_scope():
    """Downloads and Desktop, plus the game folders (ReyOS Games' library
    and "Added games are kept in")."""
    extra = [emulation.GAMES_DIR]
    storage = emulation.load_settings()["game_storage"]
    if storage:
        extra.append(storage)
    return core.quick_scope(extra)


class Scan(core.Scan):
    """v1's call shape: Scan(paths, kind, progress=...). A quick scan leaves
    disc images out (they're listed apart in the report): game ISOs and CHDs
    are over ClamAV's limits and would make every quick scan "not verified"."""

    def __init__(self, paths, kind, progress=None):
        super().__init__(paths, kind, progress=progress,
                         leave_out=core.DISC_IMAGE_EXTS if kind == "quick" else ())
