import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

SMOKE = Path(__file__).resolve().parents[1] / "tools/stable-snapshot/smoke-test.sh"
DATE = "2026/10/31"

TIMEOUT = """\
looking for conflicting packages...
:: Retrieving packages...
error: failed retrieving file 'mkinitcpio-42.2-1-any.pkg.tar.zst' from archive.archlinux.org : Operation too slow. Less than 1 bytes/sec transferred the last 10 seconds
error: failed retrieving file 'kded-6.31.0-1-x86_64.pkg.tar.zst' from archive.archlinux.org : Operation too slow. Less than 1 bytes/sec transferred the last 10 seconds
warning: too many errors from archive.archlinux.org, skipping for the remainder of this transaction
error: failed to commit transaction (unexpected error)
"""
OUTPUT = {
    "timeout": (TIMEOUT, 1),
    "checksum": ("looking for conflicting packages...\n"
                 "error: kded: signature from \"Arch Linux\" is invalid\n"
                 "error: failed to commit transaction (invalid or corrupted package (checksum))\n", 1),
    "deps": ("error: failed to prepare transaction (could not satisfy dependencies)\n"
             ":: unable to satisfy dependency 'plasma-x11-session' required by reyos-sddm\n", 1),
    "404": ("error: failed retrieving file 'kded-6.31.0-1-x86_64.pkg.tar.zst' from archive.archlinux.org : "
            "The requested URL returned error: 404\nerror: failed to commit transaction (unexpected error)\n", 1),
    # A 404 for one file while another times out is still a real failure.
    "timeout+404": (TIMEOUT + "error: failed retrieving file 'x' : The requested URL returned error: 404\n", 1),
    "ok": ("", 0),
}

# Fake pacman: each operation reads its planned results, one line per call,
# from $FAKE/<op> ("ok" once the plan runs out) and logs the call.
PACMAN = r"""#!/usr/bin/env bash
args=" $* "
case $args in
    *" -Slq "*) printf 'reyos-base\nreyos-welcome\nnvidia-580xx-utils\n'; exit 0 ;;
    *" -Syyuuw "*) op=snapdl ;;
    *" -Suu "*) op=upgrade ;;
    *" -Sw "*) op=reposdl ;;
    *" -S "*) op=install ;;
    *) echo "unexpected pacman call: $*" >&2; exit 99 ;;
esac
echo "$op $*" >> "$FAKE/calls"
n=$(grep -c "^$op " "$FAKE/calls")
what=$(sed -n "${n}p" "$FAKE/$op" 2>/dev/null)
cat "$FAKE/out-${what:-ok}"
exit "$(cat "$FAKE/rc-${what:-ok}")"
"""
CURL = r"""#!/usr/bin/env bash
echo "curl $*" >> "$FAKE/calls"
n=$(grep -c "^curl " "$FAKE/calls")
code=$(sed -n "${n}p" "$FAKE/curl" 2>/dev/null)
printf '%s' "${code:-200}"
"""
PYTHON = r"""#!/usr/bin/env bash
case $1 in
    *check-imports.py) echo "imports $*" >> "$FAKE/calls"; cat "$FAKE/imports-out"; exit "$(cat "$FAKE/imports-rc")" ;;
    *) exec "$REAL_PYTHON" "$@" ;;
esac
"""


class SmokeTestRetries(unittest.TestCase):
    """smoke-test.sh: retried downloads, classification, exit status."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.fake = self.tmp / "fake"
        self.bin = self.tmp / "bin"
        self.fake.mkdir()
        self.bin.mkdir()
        for name, body in {"pacman": PACMAN, "curl": CURL, "python3": PYTHON,
                           "pacman-key": "#!/bin/sh\nexit 0\n"}.items():
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        for what, (out, rc) in OUTPUT.items():
            (self.fake / f"out-{what}").write_text(out)
            (self.fake / f"rc-{what}").write_text(str(rc))
        self.imports("All imports and QML modules OK\n", 0)
        (self.fake / "calls").touch()

    def plan(self, op, *results):
        (self.fake / op).write_text("".join(r + "\n" for r in results))

    def imports(self, out, rc):
        (self.fake / "imports-out").write_text(out)
        (self.fake / "imports-rc").write_text(str(rc))

    def run_smoke(self):
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", FAKE=str(self.fake),
                   REAL_PYTHON=shutil.which("python3"), SMOKE_RETRY_DELAY="0",
                   SMOKE_PACMAN_CONF=str(self.tmp / "pacman.conf"),
                   SMOKE_SUMMARY=str(self.tmp / "summary.md"))
        p = subprocess.run(["bash", str(SMOKE), DATE], env=env, capture_output=True, text=True, timeout=60)
        self.summary = (self.tmp / "summary.md").read_text()
        return p.returncode

    def calls(self, op):
        return [c for c in (self.fake / "calls").read_text().splitlines() if c.startswith(op + " ")]

    def test_full_pass(self):
        self.assertEqual(self.run_smoke(), 0)
        self.assertIn("**Result: passed.**", self.summary)
        install = self.calls("install")
        self.assertEqual(len(install), 1)
        self.assertIn("reyos-base reyos-welcome", install[0])
        self.assertNotIn("nvidia", install[0])
        self.assertEqual(len(self.calls("imports")), 1)

    def test_pacman_conf_uses_only_the_snapshot(self):
        self.run_smoke()
        conf = (self.tmp / "pacman.conf").read_text()
        servers = [l.split("=", 1)[1].strip() for l in conf.splitlines() if l.startswith("Server")]
        arch = [s for s in servers if "reypaulino" not in s.lower()]
        self.assertEqual(arch, [f"https://archive.archlinux.org/repos/{DATE}/$repo/os/$arch"] * 3)
        self.assertNotIn("Include", conf)
        self.assertIn("SigLevel = Required DatabaseOptional", conf)

    def test_transient_timeout_recovers(self):
        self.plan("snapdl", "timeout", "timeout", "ok")
        self.plan("reposdl", "timeout", "ok")
        self.assertEqual(self.run_smoke(), 0)
        self.assertEqual(len(self.calls("snapdl")), 3)
        self.assertEqual(len(self.calls("reposdl")), 2)
        self.assertIn("Operation too slow, retried", self.summary)
        self.assertIn("**Result: passed.**", self.summary)

    def test_sustained_timeout_is_not_validated(self):
        self.plan("snapdl", *["timeout"] * 10)
        self.assertEqual(self.run_smoke(), 75)
        self.assertEqual(len(self.calls("snapdl")), 4)
        self.assertEqual(self.calls("upgrade"), [])
        self.assertEqual(self.calls("imports"), [])
        self.assertIn("**Result: NOT TESTED** (download failure, not validated)", self.summary)
        self.assertNotIn("passed", self.summary)

    def test_checksum_failure_is_not_retried(self):
        self.plan("snapdl", "checksum")
        self.assertEqual(self.run_smoke(), 1)
        self.assertEqual(len(self.calls("snapdl")), 1)
        self.assertIn("**Result: FAILED**", self.summary)
        self.assertIn("signature", self.summary)

    def test_checksum_failure_on_install_is_not_retried(self):
        self.plan("upgrade", "checksum")
        self.assertEqual(self.run_smoke(), 1)
        self.assertEqual(len(self.calls("upgrade")), 1)
        self.assertEqual(self.calls("install"), [])

    def test_dependency_failure_is_not_retried(self):
        self.plan("install", "deps")
        self.assertEqual(self.run_smoke(), 1)
        self.assertEqual(len(self.calls("install")), 1)
        self.assertIn("plasma-x11-session", self.summary)
        self.assertEqual(self.calls("imports"), [])

    def test_404_is_not_retried(self):
        self.plan("reposdl", "404")
        self.assertEqual(self.run_smoke(), 1)
        self.assertEqual(len(self.calls("reposdl")), 1)

    def test_404_beside_a_timeout_is_still_a_failure(self):
        self.plan("snapdl", "timeout+404")
        self.assertEqual(self.run_smoke(), 1)
        self.assertEqual(len(self.calls("snapdl")), 1)

    def test_timeout_during_install_is_not_validated_without_retry(self):
        self.plan("install", "timeout")
        self.assertEqual(self.run_smoke(), 75)
        self.assertEqual(len(self.calls("install")), 1)
        self.assertEqual(self.calls("imports"), [])

    def test_qml_failure(self):
        self.imports("FAIL: QML module org.kde.kirigami is not installed\n", 1)
        self.assertEqual(self.run_smoke(), 1)
        self.assertIn("**Result: FAILED**: imports/QML check", self.summary)
        self.assertIn("org.kde.kirigami", self.summary)

    def test_archive_unreachable_is_not_validated(self):
        (self.fake / "curl").write_text("000\n" * 10)
        self.assertEqual(self.run_smoke(), 75)
        self.assertEqual(len(self.calls("curl")), 4)
        self.assertEqual(self.calls("snapdl"), [])

    def test_missing_snapshot(self):
        (self.fake / "curl").write_text("404\n")
        self.assertEqual(self.run_smoke(), 2)
        self.assertEqual(len(self.calls("curl")), 1)
        self.assertIn("does not exist", self.summary)

    def test_bad_date(self):
        p = subprocess.run(["bash", str(SMOKE), "2026-10-31"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
