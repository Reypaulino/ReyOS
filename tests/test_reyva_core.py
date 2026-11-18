import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

BROWSER = Path(__file__).resolve().parents[1] / "reyos-packages/reyos-browser/files/usr/share/reyos/browser"
sys.path.insert(0, str(BROWSER))
import reyva_core as core  # noqa: E402


class ShieldsMatching(unittest.TestCase):
    domains = {"doubleclick.net", "tracker.example.com", "ads"}

    def test_same_rule_as_the_old_loop(self):
        def old(host):
            return any(host == d or host.endswith("." + d) for d in self.domains)
        for host in ["doubleclick.net", "ad.doubleclick.net", "a.b.doubleclick.net", "notdoubleclick.net",
                     "doubleclick.net.evil.com", "tracker.example.com", "example.com", "x.tracker.example.com",
                     "ads", "my.ads", "", "net", "doubleclick.net."]:
            self.assertEqual(core.host_blocked(host, self.domains), old(host.rstrip(".")), host)

    def test_case_and_trailing_dot(self):
        self.assertTrue(core.host_blocked("AD.DoubleClick.NET.", self.domains))

    def test_large_list_is_fast(self):
        domains = {f"tracker{i}.example{i % 97}.com" for i in range(150_000)}
        start = time.perf_counter()
        for i in range(2000):
            core.host_blocked(f"cdn{i}.static.site{i}.org", domains)
        self.assertLess(time.perf_counter() - start, 0.5)


class HttpsUpgrade(unittest.TestCase):
    def test_public_names_are_upgraded(self):
        for host in ["example.com", "www.wikipedia.org", "neverssl.com", "a.b.c.co.uk"]:
            self.assertTrue(core.should_upgrade_to_https(host), host)

    def test_local_names_and_addresses_are_not(self):
        for host in ["localhost", "127.0.0.1", "192.168.0.1", "10.1.2.3", "172.16.5.4", "[::1]", "::1",
                     "169.254.1.1", "8.8.8.8", "router", "printer.local", "nas.lan", "box.home.arpa",
                     "app.localhost", "fritz.box.internal", "dev.test", ""]:
            self.assertFalse(core.should_upgrade_to_https(host), host)

    def test_user_exception(self):
        self.assertFalse(core.should_upgrade_to_https("old.example.org", {"old.example.org"}))
        self.assertTrue(core.should_upgrade_to_https("new.example.org", {"old.example.org"}))


class Dashboard(unittest.TestCase):
    tabs = [
        {"index": 0, "title": "New Tab", "url": "file:///home.html", "home": True},
        {"index": 1, "title": "GitHub: Let's build from here", "url": "https://github.com/", "state": "frozen"},
        {"index": 2, "title": "Rust Programming Language", "url": "https://www.rust-lang.org/"},
        {"index": 3, "title": "Issues · Reypaulino/ReyOS", "url": "https://github.com/Reypaulino/ReyOS/issues"},
    ]
    bookmarks = [
        {"title": "GitHub", "url": "https://github.com/", "folder": "Dev"},
        {"title": "Arch Wiki", "url": "https://wiki.archlinux.org/"},
        {"title": "evil", "url": "javascript:alert(1)"},
    ]
    apps = [{"id": "reyos-webapp-gmail-1234abcd", "name": "Gmail", "comment": "Installed from https://mail.google.com"}]

    def test_empty_query_returns_nothing(self):
        self.assertEqual(core.dashboard_results("  ", self.tabs, self.bookmarks, self.apps), [])

    def test_open_tabs_first_and_home_tab_left_out(self):
        results = core.dashboard_results("github", self.tabs, self.bookmarks, self.apps)
        kinds = [r["kind"] for r in results]
        self.assertEqual(kinds, ["tab", "tab", "bookmark"])
        self.assertEqual(results[0]["index"], 1)  # title starts with the query
        self.assertEqual(results[0]["state"], "frozen")
        self.assertTrue(results[2]["open"])  # the bookmarked page is already an open tab

    def test_all_words_must_match(self):
        self.assertEqual([r["index"] for r in core.dashboard_results("rey issues", self.tabs, [], [])], [3])
        self.assertEqual(core.dashboard_results("rust github", self.tabs, [], []), [])

    def test_apps_and_unsafe_bookmarks(self):
        results = core.dashboard_results("gm", self.tabs, self.bookmarks, self.apps)
        self.assertEqual(results[0]["kind"], "app")
        self.assertEqual(results[0]["id"], "reyos-webapp-gmail-1234abcd")
        self.assertEqual(core.dashboard_results("evil", [], self.bookmarks, []), [])

    def test_limits(self):
        many = [{"index": i, "title": f"Doc {i}", "url": f"https://docs.example.com/{i}"} for i in range(30)]
        self.assertEqual(len(core.dashboard_results("doc", many, [], [])), core.DASHBOARD_LIMITS["tab"])

    def test_browse_one_kind_with_empty_query(self):
        tabs = core.dashboard_results("", self.tabs, self.bookmarks, self.apps, "tab")
        self.assertEqual([r["index"] for r in tabs], [1, 2, 3])
        marks = core.dashboard_results("", self.tabs, self.bookmarks, self.apps, "bookmark")
        self.assertEqual([r["title"] for r in marks], ["Arch Wiki", "GitHub"])
        self.assertEqual(core.dashboard_results("", self.tabs, self.bookmarks, self.apps, "all"), [])
        self.assertEqual([r["kind"] for r in core.dashboard_results("git", self.tabs, self.bookmarks, self.apps, "bookmark")], ["bookmark"])

    def test_bad_rows_are_skipped(self):
        rows = [{"index": "x", "title": "a", "url": "https://a.com"}, {"title": "no index", "url": "https://b.com"}, None]
        self.assertEqual(core.dashboard_results("a", [r for r in rows if r], [], []), [])


class Recovery(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_only_addresses_and_titles_are_kept(self):
        tabs = [{"url": "https://a.com/x?y=1", "title": "A", "form": "secret"}, {"url": "data:text/html,hi", "title": "D"},
                {"url": "file:///etc/passwd", "title": "F"}, {"url": "https://" + "a" * 5000 + ".com", "title": "long"},
                "junk", {"url": "view-source:https://a.com", "title": "V"}]
        self.assertEqual(core.clean_recovery_tabs(tabs), [{"url": "https://a.com/x?y=1", "title": "A"}])

    def test_clean_exit_leaves_nothing(self):
        store = core.RecoveryStore(self.dir, pid=111)
        self.assertTrue(store.save([{"url": "https://a.com", "title": "A"}], 0))
        self.assertTrue(store.data_path.exists())
        self.assertEqual(oct(store.data_path.stat().st_mode & 0o777), "0o600")
        store.stop()
        self.assertEqual(list(self.dir.iterdir()), [])
        self.assertIsNone(core.RecoveryStore(self.dir, pid=222).unclean_sessions())

    def test_running_instance_is_not_offered(self):
        first = core.RecoveryStore(self.dir, pid=111)
        first.save([{"url": "https://a.com", "title": "A"}], 0)
        second = core.RecoveryStore(self.dir, pid=222)
        # Same process holds the flock here, so simulate "another process":
        code = textwrap.dedent(f"""
            import sys; sys.path.insert(0, {str(BROWSER)!r})
            import reyva_core as c
            print(c.RecoveryStore({str(self.dir)!r}, pid=333).unclean_sessions())
        """)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, "None")
        first.stop()
        self.assertIsNone(second.unclean_sessions())

    def test_crashed_process_is_offered_once(self):
        code = textwrap.dedent(f"""
            import os, sys; sys.path.insert(0, {str(BROWSER)!r})
            import reyva_core as c
            s = c.RecoveryStore({str(self.dir)!r})
            s.save([{{"url": "https://a.com", "title": "A"}}, {{"url": "https://b.com/p", "title": "B"}}], 1)
            os._exit(9)  # dies without stop(): like a crash
        """)
        subprocess.run([sys.executable, "-c", code])
        store = core.RecoveryStore(self.dir, pid=444)
        found = store.unclean_sessions()
        self.assertEqual([t["url"] for t in found["tabs"]], ["https://a.com", "https://b.com/p"])
        self.assertEqual(found["current"], 1)
        store.discard_unclean()
        self.assertIsNone(store.unclean_sessions())
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_damaged_file_is_ignored(self):
        (self.dir / "recovery-5.json").write_text("{not json")
        (self.dir / "recovery-6.json").write_text(json.dumps({"version": 99, "tabs": [{"url": "https://a.com"}]}))
        store = core.RecoveryStore(self.dir, pid=7)
        self.assertIsNone(store.unclean_sessions())
        store.discard_all()
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_many_quick_saves_stay_valid(self):
        store = core.RecoveryStore(self.dir, pid=8)
        for i in range(200):
            store.save([{"url": f"https://a.com/{j}", "title": str(j)} for j in range(i % 15 + 1)], i)
        data = json.loads(store.data_path.read_text())
        self.assertEqual(len(data["tabs"]), 200 % 15 or 15)
        self.assertLess(data["current"], len(data["tabs"]))
        store.stop()


class WebAppLaunch(unittest.TestCase):
    def test_ids(self):
        self.assertTrue(core.valid_webapp_id("reyos-webapp-gmail-1a2b3c4d"))
        for bad in ["", "reyos-webapp-", "reyos-webapp-A", "reyos-webapp-x;rm -rf ~", "../reyos-webapp-x", None, 5]:
            self.assertFalse(core.valid_webapp_id(bad), bad)

    def test_own_desktop_entry(self):
        line = '"reyos-browser" "--app-url=https://mail.google.com/mail/u/0/" "--app-title=Gmail \\"Work\\"" "--app-icon=/home/r/.local/share/icons/x y.png"'
        self.assertEqual(core.parse_webapp_launch(line), {"url": "https://mail.google.com/mail/u/0/", "title": 'Gmail "Work"',
                                                          "icon": "/home/r/.local/share/icons/x y.png"})

    def test_portal_rewritten_entry(self):
        line = ('flatpak run --branch=stable --arch=x86_64 --command=com.reyapps.Reyva com.reyapps.Reyva '
                '"--app-url=https://example.com/a%%20b" "--app-title=Ex" "--app-icon=/x.png"')
        self.assertEqual(core.parse_webapp_launch(line)["url"], "https://example.com/a%20b")

    def test_rejects_other_schemes_and_junk(self):
        for line in ['"reyos-browser" "--app-url=file:///etc/passwd"', '"reyos-browser" "--app-url=javascript:alert(1)"',
                     "reyos-browser --app-title=x", '"unterminated', "", '"x" "--app-url=https://a.com/\nb"']:
            self.assertIsNone(core.parse_webapp_launch(line), line)

    def test_quote_round_trip(self):
        for value in ["https://example.com/a%20b?q=100%", 'Name "quoted" $HOME `x` \\back']:
            line = core.quote_desktop_exec_arg("reyos-browser") + " " + core.quote_desktop_exec_arg("--app-url=https://h.com/x") \
                + " " + core.quote_desktop_exec_arg("--app-title=" + value)
            self.assertEqual(core.parse_webapp_launch(line)["title"], value[:80])
        self.assertNotIn("%2", core.quote_desktop_exec_arg("a%20b").replace("%%", ""))

    def test_launchers_get_the_real_address(self):
        """What a desktop (GIO, as on Ubuntu) actually passes to Reyva."""
        try:
            from gi.repository import Gio, GLib
        except Exception:
            self.skipTest("GIO not available")
        url = "https://example.com/a%20b?x=50%25&t=$HOME"
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "argv.json"
            script = Path(folder) / "record.py"
            script.write_text(f"import json, sys\nopen({str(out)!r}, 'w').write(json.dumps(sys.argv[1:]))\n")
            path = Path(folder) / "t.desktop"
            path.write_text("[Desktop Entry]\nType=Application\nName=T\nExec=" + " ".join(
                core.quote_desktop_exec_arg(part) for part in (sys.executable, str(script), "--app-url=" + url)) + "\n")
            info = Gio.DesktopAppInfo.new_from_filename(str(path))
            info.launch_uris_as_manager([], None, GLib.SpawnFlags.SEARCH_PATH, None, None, None, None)
            for _ in range(50):
                if out.exists():
                    break
                time.sleep(0.1)
            self.assertEqual(json.loads(out.read_text()), ["--app-url=" + url])

    def test_desktop_entry_value(self):
        text = "[Desktop Entry]\nName=Gmail\nExec=a\n[Desktop Action x]\nExec=b\n"
        self.assertEqual(core.desktop_entry_value(text, "Exec"), "a")
        self.assertEqual(core.desktop_entry_value(text, "Icon"), "")



class ShieldsUpdateDue(unittest.TestCase):
    NOW = 1_800_000_000.0  # fixed clock

    def iso(self, seconds_ago):
        from datetime import datetime, timezone
        return datetime.fromtimestamp(self.NOW - seconds_ago, timezone.utc).isoformat(timespec="seconds")

    def test_never_downloaded_or_unreadable(self):
        for value in (None, "", "yesterday", 5):
            self.assertTrue(core.shields_update_due(value, self.NOW), value)

    def test_week_boundary(self):
        self.assertFalse(core.shields_update_due(self.iso(3600), self.NOW))
        self.assertFalse(core.shields_update_due(self.iso(7 * 86400 - 60), self.NOW))
        self.assertTrue(core.shields_update_due(self.iso(7 * 86400), self.NOW))

    def test_future_date_and_naive_date(self):
        self.assertTrue(core.shields_update_due(self.iso(-86400), self.NOW))
        naive = self.iso(3600).replace("+00:00", "")
        self.assertFalse(core.shields_update_due(naive, self.NOW))


if __name__ == "__main__":
    unittest.main()
