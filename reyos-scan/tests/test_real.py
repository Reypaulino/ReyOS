"""Against the real ClamAV with real definitions (skipped without them).
Each scan loads the definitions first (about 10-15 s), so this takes a
couple of minutes. REYOS_SCAN_SLOW=1 adds a 450 MB-unpacked archive (about 1.5 minutes).

Known ClamAV 1.5.4 gap, found here (not tested, nothing to assert): a
zip whose entry has a zip64 local header and a data descriptor (Python's
ZipFile.open(..., "w", force_zip64=True)) is reported OK without being
unpacked, EICAR inside included. See docs/ubuntu-scan-testing.md."""
import io
import os
import re
import threading
import time
import unittest
import zipfile

from helpers import EICAR, TempHome, core

HAVE_DEFS = core.installed() and core.definitions()["version"]


def zipped(name, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, data)
    return buf.getvalue()


@unittest.skipUnless(HAVE_DEFS, "needs clamscan with definitions")
class TestRealClamAV(TempHome):
    def scan(self, *rel, kind="folder"):
        t = time.time()
        r = core.Scan([self.home / p for p in rel] or [self.home], kind).run()
        print(f"\n  {self.id().rsplit('.', 1)[1]}: {r['status']}, {r['files']} files, {time.time() - t:.1f} s")
        return r

    def test_clean_folder(self):
        self.write("Downloads/notes.txt", b"just text\n")
        self.write("Downloads/archive.zip", zipped("a.txt", b"nothing here"))
        self.assertEqual(self.scan("Downloads")["status"], "clean")

    def test_eicar_plain_exe_dll_and_zip(self):
        for rel in ("Downloads/eicar.com", "Downloads/setup.exe", "Downloads/lib/x.dll"):
            self.write(rel, EICAR)
        self.write("Downloads/eicar.zip", zipped("inside/eicar.exe", EICAR))
        r = self.scan("Downloads")
        self.assertEqual(r["status"], "found")
        self.assertEqual(len(r["findings"]), 4)
        self.assertTrue(all("Eicar" in f["signature"] or "EICAR" in f["signature"] for f in r["findings"]))

    def test_symlink_loop_and_link_outside(self):
        d = self.home / "Downloads/loop"
        d.mkdir(parents=True)
        os.symlink(d, d / "again")
        os.symlink("/", d / "root")
        self.write("outside/eicar.com", EICAR)
        os.symlink(self.home / "outside", d / "elsewhere")
        r = self.scan("Downloads")
        self.assertEqual(r["status"], "clean")

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_unreadable_file_is_not_verified(self):
        self.write("Downloads/locked.exe", EICAR[:10], mode=0o000)
        self.write("Downloads/ok.txt")
        r = self.scan("Downloads")
        self.assertEqual(r["status"], "not_verified")
        self.assertEqual([e.rsplit(": ", 1)[1] for e in r["errors"]], ["Access denied"])

    def test_nested_archive_over_recursion_limit(self):
        data, name = b"plain text", "a.txt"
        for i in range(20):
            data, name = zipped(name, data), f"level{i}.zip"
        self.write("Downloads/deep.zip", data)
        r = self.scan("Downloads")
        self.assertEqual(r["status"], "not_verified")
        self.assertTrue(r["skipped"])

    def test_archive_bomb_over_size_limit(self):
        # Small limits so this takes seconds: same mechanism as the real ones.
        saved = core.LIMITS
        core.LIMITS = [re.sub(r"=\d+M$", "=40M", o) for o in saved]
        try:
            zeros = self.home / "zeros.bin"
            with open(zeros, "wb") as f:
                f.truncate(100 << 20)
            p = self.home / "Downloads/bomb.zip"
            p.parent.mkdir(parents=True)
            with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(zeros, "zeros.bin")
            zeros.unlink()
            r = self.scan("Downloads")
        finally:
            core.LIMITS = saved
        self.assertLess(p.stat().st_size, 1 << 20)
        self.assertEqual(r["status"], "not_verified")
        self.assertEqual((r["findings"], r["errors"]), ([], []))
        self.assertTrue(r["skipped"][0]["reason"].startswith(core.LIMIT_SIGNATURE))

    def test_member_over_file_limit_is_flagged(self):
        # A signature that matches anywhere in a file (EICAR only matches
        # at the start), with core's limits scaled down to 40M: a marked
        # 30M member must be found, a 100M one reported as not checked.
        marker = b"REYOSSCANMARKER0123456789"
        ndb = self.tmp / "marker.ndb"
        ndb.write_text(f"ReyOS.Test.Marker:0:*:{marker.hex()}\n")
        saved = core.LIMITS
        core.LIMITS = [re.sub(r"=\d+M$", "=40M", o) for o in saved] + [f"--database={ndb}"]
        try:
            for n in (30, 100):
                raw = self.home / f"m{n}.bin"
                with open(raw, "wb") as f:
                    f.truncate(n << 20)
                with open(raw, "ab") as f:
                    f.write(marker)
                folder = self.home / f"Downloads/m{n}"
                folder.mkdir(parents=True)
                with zipfile.ZipFile(folder / "m.zip", "w", zipfile.ZIP_DEFLATED) as z:
                    z.write(raw, "m.bin")
                raw.unlink()
            small, big = self.scan("Downloads/m30"), self.scan("Downloads/m100")
        finally:
            core.LIMITS = saved
        self.assertEqual(small["status"], "found")
        self.assertEqual(big["status"], "not_verified")
        self.assertTrue(big["skipped"])

    def test_limits_shape(self):
        opts = dict(o.split("=", 1) for o in core.LIMITS)
        self.assertGreaterEqual(int(opts["--max-filesize"][:-1]), int(opts["--max-scansize"][:-1]))

    @unittest.skipUnless(os.environ.get("REYOS_SCAN_SLOW"), "set REYOS_SCAN_SLOW=1")
    def test_archive_under_limits_is_fully_checked(self):
        # 450 MB of zeros in a 0.5 MB zip: under the real limits, so
        # ClamAV unpacks and checks all of it (600 MB measured at about 1m45 of CPU).
        zeros = self.home / "zeros.bin"
        with open(zeros, "wb") as f:
            f.truncate(450 << 20)
        p = self.home / "Downloads/big.zip"
        p.parent.mkdir(parents=True)
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(zeros, "zeros.bin")
        zeros.unlink()
        self.assertEqual(self.scan("Downloads")["status"], "clean")

    def test_cancel(self):
        for i in range(200):
            self.write(f"Downloads/f{i}.txt", os.urandom(4096))
        scan = core.Scan([self.home / "Downloads"], "folder")
        threading.Timer(3, scan.cancel).start()
        t = time.time()
        r = scan.run()
        self.assertEqual(r["status"], "cancelled")
        self.assertLess(time.time() - t, 20)

    def test_game_check_quarantine_restore(self):
        exe = self.write("Games/Bad/game.exe", b"MZ fine")
        self.write("Games/Bad/bin/hook.dll", EICAR)
        r = core.check_program(exe)
        self.assertEqual(r["status"], "found")
        (finding,) = r["findings"]
        ok, msg = core.quarantine(finding["path"], finding["signature"])
        self.assertTrue(ok, msg)
        self.assertEqual(core.check_program(exe)["status"], "clean")
        r = core.check_program(exe)
        self.assertEqual((r["status"], r["checked_before"]), ("clean", 1))
        ok, msg = core.restore(core.quarantined()[0]["id"])
        self.assertTrue(ok, msg)
        self.assertEqual(core.sha256(finding["path"]), finding["sha256"])


if __name__ == "__main__":
    unittest.main()
