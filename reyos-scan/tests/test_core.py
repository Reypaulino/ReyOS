"""Core logic against a fake clamscan: parsing, statuses, cache,
quarantine. Runs anywhere (no ClamAV needed)."""
import json
import os
import stat
import threading
import time
import unittest
from pathlib import Path

from helpers import ROOT, TempHome, core
from reyos_scan import cli

FAKE = ROOT / "tests" / "fake-clamscan"


class FakeClam(TempHome):
    def setUp(self):
        super().setUp()
        bindir = self.tmp / "bin"
        bindir.mkdir()
        (bindir / "clamscan").symlink_to(FAKE)
        os.environ["PATH"] = f"{bindir}:{os.environ.get('PATH', '/usr/bin:/bin')}"
        self.out = self.tmp / "clam-out.txt"
        self.args = self.tmp / "clam-args.txt"
        os.environ["FAKE_CLAM_OUT"] = str(self.out)
        os.environ["FAKE_CLAM_ARGS"] = str(self.args)

    def clam(self, lines, rc=0):
        self.out.write_text("".join(line + "\n" for line in lines))
        os.environ["FAKE_CLAM_RC"] = str(rc)


class TestScan(FakeClam):
    def test_clean(self):
        f = self.write("Downloads/a.txt")
        self.clam([f"Scanning {f}", f"{f}: OK"])
        r = core.Scan([f.parent], "folder").run()
        self.assertEqual((r["status"], r["files"]), ("clean", 1))
        self.assertEqual(r["definitions"], "27800")
        self.assertEqual(core.last_report()["status"], "clean")

    def test_found_records_hash_and_size(self):
        f = self.write("Downloads/bad.exe", b"evil")
        self.clam([f"Scanning {f}", f"{f}: Win.Test.EICAR_HDB-1 FOUND"], rc=1)
        r = core.Scan([f.parent], "folder").run()
        self.assertEqual(r["status"], "found")
        self.assertEqual(r["findings"][0]["signature"], "Win.Test.EICAR_HDB-1")
        self.assertEqual(r["findings"][0]["sha256"], core.sha256(f))
        self.assertEqual(r["findings"][0]["size"], 4)

    def test_path_with_colon_and_spaces(self):
        f = self.write("Downloads/odd: name here.exe", b"x")
        self.clam([f"Scanning {f}", f"{f}: Some.Sig FOUND"], rc=1)
        r = core.Scan([f.parent], "folder").run()
        self.assertEqual(r["findings"][0]["path"], str(f))

    def test_read_error_is_not_verified(self):
        f = self.write("Downloads/locked.bin")
        self.clam([f"Scanning {f}", f"{f}: Can't open file or directory ERROR"], rc=2)
        r = core.Scan([f.parent], "folder").run()
        self.assertEqual(r["status"], "not_verified")
        self.assertIn("couldn't be read", r["summary"])

    def test_access_denied_without_error_suffix(self):
        f = self.write("Downloads/locked.exe")
        self.clam([f"{f}: Access denied"], rc=2)
        r = core.Scan([f.parent], "folder").run()
        self.assertEqual(r["errors"], [f"{f}: Access denied"])

    def test_benign_lines(self):
        d = self.home / "Downloads"
        self.clam([f"{d}/empty: Empty file", f"{d}/link: Symbolic link", f"Scanning {d}/a", f"{d}/a: OK"])
        self.assertEqual(core.Scan([d], "folder").run()["status"], "clean")

    def test_limits_are_skipped_not_threats(self):
        f = self.write("Downloads/bomb.zip")
        self.clam([f"Scanning {f}", f"{f}: Heuristics.Limits.Exceeded.MaxFileSize FOUND",
                   f"{f}: Virus(es) detected ERROR"], rc=2)
        r = core.Scan([f.parent], "folder").run()
        self.assertEqual(r["status"], "not_verified")
        self.assertEqual((r["findings"], r["errors"]), ([], []))
        self.assertEqual(r["skipped"][0]["path"], str(f))
        self.assertIn("too big", r["summary"])

    def test_nonzero_exit_without_details_is_not_clean(self):
        self.clam(["LibClamAV Error: something broke"], rc=2)
        r = core.Scan([self.home], "home").run()
        self.assertEqual(r["status"], "not_verified")

    def test_no_definitions(self):
        os.environ["FAKE_CLAM_NODEFS"] = "1"
        r = core.Scan([self.home], "home").run()
        self.assertEqual(r["status"], "not_verified")
        self.assertIn("definitions", r["summary"])

    def test_not_installed(self):
        os.environ["PATH"] = str(self.tmp / "empty")
        r = core.Scan([self.home], "home").run()
        self.assertEqual(r["status"], "not_verified")
        self.assertIn("isn't installed", r["summary"])

    def test_safe_options(self):
        self.clam([])
        core.Scan([self.home], "home").run()
        args = self.args.read_text().split("\n")
        for opt in ("--cross-fs=no", "--follow-dir-symlinks=0", "--follow-file-symlinks=0", "--alert-exceeds-max=yes"):
            self.assertIn(opt, args)
        self.assertEqual(args[args.index("--") + 1], str(self.home))
        self.assertTrue(any(a.startswith("--exclude-dir=^") and "quarantine" in a for a in args))

    def test_file_list(self):
        a, b = self.write("g/a.exe"), self.write("g/b.dll")
        self.clam([f"Scanning {a}", f"{a}: OK", f"Scanning {b}", f"{b}: OK"])
        r = core.Scan([a.parent], "addgame", files=[a, b]).run()
        self.assertEqual(r["status"], "clean")
        args = self.args.read_text().split("\n")
        self.assertNotIn("--", args)
        self.assertTrue(any(x.startswith("--file-list=") for x in args))
        self.assertEqual(list((Path(os.environ.get("TMPDIR", "/tmp"))).glob("reyos-scan-*.txt")), [])

    def test_empty_file_list(self):
        r = core.Scan([self.home], "addgame", files=[]).run()
        self.assertEqual(r["status"], "clean")
        self.assertFalse(self.args.exists())

    def test_cancel(self):
        self.clam([f"Scanning {self.home}/x"])
        os.environ["FAKE_CLAM_SLEEP"] = "30"
        scan = core.Scan([self.home], "home")
        threading.Timer(0.5, scan.cancel).start()
        t = time.time()
        r = scan.run()
        self.assertLess(time.time() - t, 10)
        self.assertEqual(r["status"], "cancelled")

    def test_reports_are_private_and_unique(self):
        self.clam([])
        core.Scan([self.home], "home").run()
        core.Scan([self.home], "home").run()
        self.assertEqual(len(list(core.REPORTS.glob("*.json"))), 2)
        self.assertEqual(stat.S_IMODE(os.stat(core.DATA).st_mode), 0o700)
        self.assertEqual(len(core.history()), 2)


class TestProgramCheck(FakeClam):
    def test_program_files(self):
        exe = self.write("Games/X/setup.exe")
        self.write("Games/X/data/lib.dll")
        self.write("Games/X/readme.txt")
        os.symlink("/etc/passwd", self.home / "Games/X/link.dll")
        names = sorted(p.name for p in core.program_files(exe))
        self.assertEqual(names, ["lib.dll", "setup.exe"])

    def test_downloads_only_the_file(self):
        exe = self.write("Downloads/setup.exe")
        self.write("Downloads/other.exe")
        self.assertEqual(core.program_files(exe), [exe])

    def test_cache_skips_unchanged_files(self):
        exe = self.write("Games/X/game.exe", b"v1")
        dll = self.write("Games/X/a.dll", b"d")
        self.clam([f"Scanning {exe}", f"{exe}: OK", f"Scanning {dll}", f"{dll}: OK"])
        self.assertEqual(core.check_program(exe)["status"], "clean")
        r = core.check_program(exe)
        self.assertEqual((r["status"], r["checked_before"]), ("clean", 2))
        exe.write_bytes(b"v2")
        r = core.check_program(exe)
        self.assertEqual(r["checked_before"], 1)
        listed = [a for a in self.args.read_text().split("\n") if a.startswith("--file-list=")]
        self.assertTrue(listed)

    def test_found_is_not_cached(self):
        exe = self.write("Games/X/game.exe", b"v1")
        self.clam([f"Scanning {exe}", f"{exe}: Bad.Sig FOUND"], rc=1)
        self.assertEqual(core.check_program(exe)["status"], "found")
        self.assertFalse(core.CACHE.exists())

    def test_new_definitions_rescan(self):
        exe = self.write("Games/X/game.exe")
        self.clam([f"Scanning {exe}", f"{exe}: OK"])
        core.check_program(exe)
        core.CACHE.write_text(json.dumps({k: "27799" for k in json.loads(core.CACHE.read_text())}))
        self.assertEqual(core.check_program(exe)["checked_before"], 0)


class TestQuarantine(TempHome):
    def test_roundtrip(self):
        f = self.write("Downloads/bad.exe", b"payload", mode=0o755)
        digest = core.sha256(f)
        ok, _ = core.quarantine(f, "Sig")
        self.assertTrue(ok)
        self.assertFalse(f.exists())
        (item,) = core.quarantined()
        data = core.QUARANTINE / f"{item['id']}.quarantined"
        self.assertEqual(stat.S_IMODE(os.stat(data).st_mode), 0o400)
        self.assertEqual(stat.S_IMODE(os.stat(core.QUARANTINE).st_mode), 0o700)
        self.assertEqual(item["sha256"], digest)
        ok, msg = core.restore(item["id"])
        self.assertTrue(ok, msg)
        self.assertEqual(core.sha256(f), digest)
        self.assertEqual(stat.S_IMODE(os.stat(f).st_mode), 0o755)
        self.assertEqual(core.quarantined(), [])

    def test_restore_does_not_overwrite(self):
        f = self.write("Downloads/a.exe", b"old")
        core.quarantine(f)
        self.write("Downloads/a.exe", b"new")
        ok, msg = core.restore(core.quarantined()[0]["id"])
        self.assertTrue(ok)
        self.assertEqual(f.read_bytes(), b"new")
        self.assertEqual((f.parent / "a (restored 1).exe").read_bytes(), b"old")

    def test_tampered_copy_is_not_restored(self):
        f = self.write("Downloads/a.exe", b"old")
        core.quarantine(f)
        item = core.quarantined()[0]
        data = core.QUARANTINE / f"{item['id']}.quarantined"
        os.chmod(data, 0o600)
        data.write_bytes(b"changed")
        ok, _ = core.restore(item["id"])
        self.assertFalse(ok)
        self.assertFalse(f.exists())

    def test_refuses_symlinks_and_folders(self):
        target = self.write("real.txt")
        link = self.home / "Downloads/link.exe"
        link.parent.mkdir(exist_ok=True)
        link.symlink_to(target)
        self.assertFalse(core.quarantine(link)[0])
        self.assertTrue(target.exists() and link.is_symlink())
        self.assertFalse(core.quarantine(self.home / "Downloads")[0])

    def test_bad_ids(self):
        for qid in ("", "../../etc/passwd", "20261026-120000-zzzzzzzz", None):
            self.assertFalse(core.restore(qid)[0])
            self.assertFalse(core.delete(qid)[0])

    def test_delete(self):
        f = self.write("Downloads/a.exe")
        core.quarantine(f)
        ok, _ = core.delete(core.quarantined()[0]["id"])
        self.assertTrue(ok)
        self.assertEqual(list(core.QUARANTINE.iterdir()), [])


class TestCli(FakeClam):
    def test_exit_codes(self):
        f = self.write("Downloads/bad.exe", b"x")
        self.clam([f"Scanning {f}", f"{f}: Sig FOUND"], rc=1)
        self.assertEqual(cli.main(["scan", "--json", str(f.parent)]), 1)
        self.clam([f"Scanning {f}", f"{f}: OK"])
        self.assertEqual(cli.main(["scan", "--json", "--quick"]), 0)
        self.clam([f"{f}: Access denied ERROR"], rc=2)
        self.assertEqual(cli.main(["check", "--json", str(f)]), 2)

    def test_delete_needs_yes(self):
        self.assertEqual(cli.main(["quarantine", "delete", "20261026-120000-0000abcd"]), 2)

    def test_run_checked_refuses_threat(self):
        exe = self.write("Games/X/game.exe")
        marker = self.tmp / "ran"
        self.clam([f"Scanning {exe}", f"{exe}: Sig FOUND"], rc=1)
        self.assertEqual(cli.main(["run-checked", str(exe), "--", "touch", str(marker)]), 1)
        self.assertFalse(marker.exists())


class TestReyOSCopy(unittest.TestCase):
    """ReyOS Control Center ships a copy of core.py: it must stay identical."""
    COPY = ROOT.parent / "reyos-packages/reyos-control-center-gui/files/usr/share/reyos/control-center/reyos_scan_core.py"

    def test_identical(self):
        if not self.COPY.exists():
            self.skipTest("ReyOS adapter not added yet")
        self.assertEqual(self.COPY.read_bytes(), (ROOT / "reyos_scan/core.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
