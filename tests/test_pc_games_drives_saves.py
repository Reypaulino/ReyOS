import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

CC = Path(__file__).resolve().parents[1] / "reyos-packages/reyos-control-center-gui/files/usr/share/reyos/control-center"
sys.path.insert(0, str(CC))
spec = importlib.util.spec_from_file_location("pc_games", CC / "pc_games.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


class DriveTests(unittest.TestCase):
    def test_drive_of_missing(self):
        self.assertEqual(pc._drive_of_missing("/run/media/reyrubi/ReyGames/Games/pc/speed.exe"), "ReyGames")
        self.assertEqual(pc._drive_of_missing("/run/media/reyrubi/d70fa032-44b2/home/x.exe"), "d70fa032-44b2")
        self.assertEqual(pc._drive_of_missing("/home/reyrubi/Games/x.exe"), "")

    def test_temporary_drive(self):
        with patch.object(pc, "_mount_point", return_value=Path("/run/media/reyrubi/ReyGames")), \
             patch.object(pc, "_fstab_mounts", return_value=set()):
            self.assertEqual(pc.temporary_drive("/run/media/reyrubi/ReyGames/g.exe"), "ReyGames")
        with patch.object(pc, "_mount_point", return_value=Path("/mnt/ubuntu")), \
             patch.object(pc, "_fstab_mounts", return_value={"/mnt/ubuntu"}):
            self.assertEqual(pc.temporary_drive("/mnt/ubuntu/g.exe"), "")
        with patch.object(pc, "_mount_point", return_value=Path("/run/media/reyrubi/ReyGames")), \
             patch.object(pc, "_fstab_mounts", return_value={"/run/media/reyrubi/ReyGames"}):
            self.assertEqual(pc.temporary_drive("/run/media/reyrubi/ReyGames/g.exe"), "")
        with patch.object(pc, "_mount_point", return_value=Path("/")), \
             patch.object(pc, "_fstab_mounts", return_value={"/"}):
            self.assertEqual(pc.temporary_drive("/home/reyrubi/g.exe"), "")


class SavesTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.saves = self.root / "Saves" / "PC"
        patch.object(pc, "SAVES", self.saves).start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.dir.cleanup()

    def kept(self, name, files, age=0):
        folder = self.saves / name
        for rel in files:
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            (folder / rel).write_text("save")
        t = time.time() - age
        os.utime(folder, (t, t))
        return folder

    def test_match_longer_and_shorter_names(self):
        old = self.kept("need-for-speed-most-wanted", ["Documents/NFS Most Wanted/Rey/Rey"])
        self.assertEqual(pc.kept_saves_for("Need for Speed Most Wanted Black Edition"), old)
        self.assertEqual(pc.kept_saves_for("Need for Speed: Most Wanted"), old)
        self.assertIsNone(pc.kept_saves_for("Need for Speed Underground"))
        self.assertIsNone(pc.kept_saves_for("Need"))

    def test_newest_copy_wins_and_empty_ignored(self):
        self.kept("prince-of-persia", ["Game folder/Save/a.sav"], age=1000)
        newer = self.kept("prince-of-persia-2", ["Game folder/Save/a.sav"])
        (self.saves / "prince-of-persia-3").mkdir()
        self.assertEqual(pc.kept_saves_for("Prince of Persia"), newer)

    def test_restore_never_overwrites(self):
        kept = self.kept("nfs", ["Documents/NFS/Rey/Rey", "Documents/NFS/Rey/other", "Game folder/Saves/s1"])
        prefix = self.root / "prefix"
        user = prefix / "drive_c" / "users" / "steamuser"
        (user / "Documents" / "NFS" / "Rey").mkdir(parents=True)
        (user / "Documents" / "NFS" / "Rey" / "Rey").write_text("newer")
        game = self.root / "games" / "Need For Speed"
        game.mkdir(parents=True)
        exe = game / "speed.exe"
        exe.write_text("")
        with patch.object(pc, "games_dir", return_value=self.root / "games-library"):
            copied = pc.restore_saves(kept, prefix, exe)
        self.assertEqual(copied, 2)
        self.assertEqual((user / "Documents/NFS/Rey/Rey").read_text(), "newer")
        self.assertTrue((user / "Documents/NFS/Rey/other").exists())
        self.assertTrue((game / "Saves" / "s1").exists())


if __name__ == "__main__":
    unittest.main()
