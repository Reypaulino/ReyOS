import sys
import unittest
from pathlib import Path

CC = Path(__file__).resolve().parents[1] / "reyos-packages/reyos-control-center-gui/files/usr/share/reyos/control-center"
sys.path.insert(0, str(CC))
import update_errors  # noqa: E402

# The laptop's /var/log/reyos-update.log, 2026-11-23 09:51 (shortened package list).
LAPTOP_2026_11_23 = """\
:: Synchronizing package databases...
 reyos-local downloading...
 core downloading...
:: Starting full system upgrade...
resolving dependencies...
Packages (207) alsa-card-profiles-1:1.6.11-2  linux-7.3.5.arch1-1
:: Proceed with installation? [Y/n]
:: Retrieving packages...
 linux-7.3.5.arch1-1-x86_64 downloading...
error: failed retrieving file 'linux-lts-6.18.64-1-x86_64.pkg.tar.zst' from archive.archlinux.org : Connection timed out after 10001 milliseconds
error: failed retrieving file 'linux-7.3.5.arch1-1-x86_64.pkg.tar.zst' from archive.archlinux.org : Connection timed out after 10001 milliseconds
warning: too many errors from archive.archlinux.org, skipping for the remainder of this transaction
warning: failed to retrieve some files
error: failed to commit transaction (download library error)
Errors occurred, no packages were upgraded.
""".splitlines()


def explain(text, what="Update"):
    return update_errors.explain(text.splitlines(), what)


class Explain(unittest.TestCase):
    def test_laptop_archive_timeout(self):
        msg = update_errors.explain(LAPTOP_2026_11_23, "Full update")
        self.assertTrue(msg.startswith("Full update failed: couldn't download from Arch's package archive (archive.archlinux.org)"), msg)
        self.assertIn("try again later", msg)
        self.assertTrue(msg.endswith("Nothing was changed."), msg)

    def test_database_sync_failure(self):
        msg = explain(":: Synchronizing package databases...\n"
                      "error: failed retrieving file 'core.db' from archive.archlinux.org : Operation too slow. Less than 1 bytes/sec transferred the last 10 seconds\n"
                      "error: failed to synchronize all databases (download library error)")
        self.assertIn("archive.archlinux.org", msg)
        self.assertIn("Nothing was changed.", msg)

    def test_reyos_server(self):
        msg = explain("error: failed retrieving file 'reyos-local.db' from reypaulino.github.io : Could not resolve host: reypaulino.github.io\n"
                      "error: failed to synchronize all databases (download library error)")
        self.assertIn("the ReyOS package server", msg)

    def test_disk_full(self):
        msg = explain("error: Partition / too full: 63326 blocks needed, 12000 blocks free\n"
                      "error: not enough free disk space\nerror: failed to commit transaction (not enough free disk space)\n"
                      "Errors occurred, no packages were upgraded.")
        self.assertEqual(msg, "Update failed: not enough disk space. Free some space and try again. Nothing was changed.")

    def test_lock(self):
        msg = explain("error: failed to init transaction (unable to lock database)\n"
                      "error: could not lock database: File exists")
        self.assertIn("another update is still running", msg)

    def test_signature(self):
        msg = explain("error: reyos-base: signature from \"ReyOS Package Signing <x>\" is unknown trust\n"
                      ":: File /var/cache/pacman/pkg/reyos-base.pkg.tar.zst is corrupted (invalid or corrupted package (PGP signature)).\n"
                      "error: failed to commit transaction (invalid or corrupted package (PGP signature))\n"
                      "Errors occurred, no packages were upgraded.")
        self.assertIn("signature couldn't be checked", msg)
        self.assertIn("Nothing was changed.", msg)

    def test_checksum(self):
        msg = explain("error: linux: checksum is invalid (invalid or corrupted package (checksum))\n"
                      "error: failed to commit transaction (invalid or corrupted package)")
        self.assertIn("download arrived damaged", msg)

    def test_dependency(self):
        msg = explain("error: failed to prepare transaction (could not satisfy dependencies)\n"
                      ":: unable to satisfy dependency 'qt6-base=6.12.0' required by qt6-webengine")
        self.assertIn("dependency problem", msg)
        self.assertNotIn("Nothing was changed", msg)

    def test_file_conflict(self):
        msg = explain("error: failed to commit transaction (conflicting files)\n"
                      "foo: /usr/bin/foo exists in filesystem\nErrors occurred, no packages were upgraded.")
        self.assertIn("already exists", msg)

    def test_sudo(self):
        self.assertIn("sudo refused", explain("sudo: a password is required"))

    def test_unknown_error_uses_last_error_line(self):
        msg = explain("error: something new went wrong", "Switching to the Stable channel")
        self.assertEqual(msg, "Switching to the Stable channel failed: something new went wrong")

    def test_no_output(self):
        self.assertEqual(update_errors.explain([]), "Update failed. See the log above for details.")

    def test_package_names_dont_trigger(self):
        # "Packages (3) libcheck-1 timeout-2" must not count as an error line.
        msg = explain("Packages (2) checksum-tools-1 timed-1\nerror: something else")
        self.assertEqual(msg, "Update failed: something else")


if __name__ == "__main__":
    unittest.main()
