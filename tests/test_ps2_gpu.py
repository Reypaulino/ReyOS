import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# emulation.py builds its paths from the home folder at import time.
HOME = tempfile.TemporaryDirectory()
os.environ["HOME"] = HOME.name

CC = Path(__file__).resolve().parents[1] / "reyos-packages/reyos-control-center-gui/files/usr/share/reyos/control-center"
sys.path.insert(0, str(CC))
spec = importlib.util.spec_from_file_location("emulation", CC / "emulation.py")
emu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emu)

EXT = "org.freedesktop.Platform.GL.nvidia-580-178-04"


class Ps2GpuTests(unittest.TestCase):
    """Separate graphics card for PC games (game_gpu) and PS2 (ps2_gpu)."""

    def setUp(self):
        (Path(HOME.name) / ".local/share/flatpak/runtime" / EXT).mkdir(parents=True, exist_ok=True)
        emu.REYOS_CFG_DIR.mkdir(parents=True, exist_ok=True)
        emu.SETTINGS_JSON.unlink(missing_ok=True)
        emu.PCSX2_INI.unlink(missing_ok=True)
        self.patches = [patch.object(emu, "nvidia_offload_ready", return_value=True),
                        patch.object(emu, "nvidia_flatpak_extensions", return_value=[EXT, EXT.replace("GL.", "GL32.")]),
                        patch.object(emu, "write_retroarch_cfg")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def settings(self, **values):
        emu.SETTINGS_JSON.write_text(json.dumps(values))

    def ini(self, adapter):
        emu.PCSX2_INI.parent.mkdir(parents=True, exist_ok=True)
        emu.PCSX2_INI.write_text(f"[EmuCore/GS]\nRenderer = 14\nAdapter = {adapter}\n")

    def test_defaults(self):
        self.assertEqual(emu.load_settings()["ps2_gpu"], "builtin")
        self.assertTrue(emu.games_use_nvidia())
        self.assertFalse(emu.pcsx2_on_nvidia())
        self.assertEqual(emu.pcsx2_run_args(), [])

    def test_pc_games_and_ps2_are_separate(self):
        self.settings(game_gpu="builtin", ps2_gpu="nvidia")
        self.assertFalse(emu.games_use_nvidia())
        self.assertTrue(emu.pcsx2_on_nvidia())
        self.assertIn("--env=__NV_PRIME_RENDER_OFFLOAD=1", emu.pcsx2_run_args())

    def test_bad_value(self):
        self.settings(ps2_gpu="amd")
        self.assertEqual(emu.load_settings()["ps2_gpu"], "builtin")
        emu.save_settings({"ps2_gpu": "nvidia"})
        self.assertEqual(emu.load_settings()["ps2_gpu"], "nvidia")

    def test_adapter_picked_in_pcsx2_is_kept(self):
        self.settings(ps2_gpu="nvidia")
        self.ini("Intel(R) HD Graphics 630 (KBL GT2)")
        self.assertFalse(emu.pcsx2_on_nvidia())
        lines = emu.PCSX2_INI.read_text().splitlines()
        emu._apply_pcsx2_gpu(lines, emu.load_settings())
        self.assertEqual(emu._ini_get(lines, "EmuCore/GS", "Adapter"), "Intel(R) HD Graphics 630 (KBL GT2)")
        self.ini("NVIDIA GeForce 940MX")
        self.assertTrue(emu.pcsx2_on_nvidia())

    def test_no_nvidia_driver(self):
        self.settings(ps2_gpu="nvidia")
        with patch.object(emu, "nvidia_offload_ready", return_value=False):
            self.assertFalse(emu.pcsx2_on_nvidia())


if __name__ == "__main__":
    unittest.main()
