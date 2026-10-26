"""Shared setup: each test gets its own HOME and data folder, so nothing
touches the real ~/.local/share/reyos/security."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reyos_scan import core  # noqa: E402

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
assert len(EICAR) == 68


class TempHome(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reyos-scan-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self._env = dict(os.environ)
        os.environ["HOME"] = str(self.home)
        data = self.home / ".local/share/reyos/security"
        self._paths = (core.DATA, core.REPORTS, core.QUARANTINE, core.CACHE)
        core.DATA, core.REPORTS, core.QUARANTINE, core.CACHE = (
            data, data / "scans", data / "quarantine", data / "cache.json")

    def tearDown(self):
        core.DATA, core.REPORTS, core.QUARANTINE, core.CACHE = self._paths
        os.environ.clear()
        os.environ.update(self._env)
        for dirpath, dirnames, _ in os.walk(self.tmp):
            for d in dirnames:
                try:
                    os.chmod(os.path.join(dirpath, d), 0o700)
                except OSError:
                    pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, data=b"hello\n", mode=None):
        p = self.home / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        if mode is not None:
            os.chmod(p, mode)
        return p
