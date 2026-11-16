import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "reyos-packages"
CC = ROOT / "reyos-control-center-gui/files/usr/share/reyos/control-center"
sys.path.insert(0, str(CC))
import kernel_status  # noqa: E402

loader = importlib.machinery.SourceFileLoader(
    "check_updates", str(ROOT / "reyos-update-notifier/files/usr/share/reyos/bin/reyos-check-updates"))
spec = importlib.util.spec_from_loader("check_updates", loader)
notifier = importlib.util.module_from_spec(spec)
loader.exec_module(notifier)

REAL = os.uname()


def uname(release):
    return lambda: type(REAL)((REAL.sysname, REAL.nodename, release, REAL.version, REAL.machine))


def pacman_owns(owned):
    return lambda *a, **k: subprocess.CompletedProcess(a, 0 if owned else 1)


class KernelStatusTests(unittest.TestCase):
    """Restart needed after a kernel update (laptop 2026-11-16)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.modules = Path(self.tmp.name)
        (self.modules / "7.2.11-arch1-1").mkdir()
        (self.modules / "7.2.11-arch1-1" / "modules.dep").write_text("")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, release, owned):
        with patch.object(kernel_status, "MODULES", self.modules), \
             patch("os.uname", uname(release)), \
             patch("subprocess.run", pacman_owns(owned)):
            cc = kernel_status.status()
        with patch.object(notifier, "Path", lambda p: self.modules if p == "/usr/lib/modules" else Path(p)), \
             patch("os.uname", uname(release)), \
             patch("subprocess.run", pacman_owns(owned)):
            self.assertEqual(notifier.kernel_replaced(), cc["needed"])
        return cc

    def test_installed_kernel(self):
        self.assertEqual(self.check("7.2.11-arch1-1", True),
                         {"needed": False, "modulesMissing": False, "running": "7.2.11-arch1-1"})

    def test_modules_removed_by_update(self):
        st = self.check("7.1.0-arch1-1", True)
        self.assertTrue(st["needed"])
        self.assertTrue(st["modulesMissing"])

    def test_modules_kept_by_hook(self):
        # kernel-modules-hook's restored copy: modules there, owned by nothing.
        st = self.check("7.2.11-arch1-1", False)
        self.assertTrue(st["needed"])
        self.assertFalse(st["modulesMissing"])

    def test_wsl_kernel_ignored(self):
        st = self.check("6.6.87.2-microsoft-standard-WSL2", False)
        self.assertFalse(st["needed"])


if __name__ == "__main__":
    unittest.main()
