"""Reyva's Python backend (main.py) without a window: imports, launchers,
settings. Needs PySide6 (run with the .deb's venv or inside the Flatpak):

    /opt/reyos-browser/.venv/bin/python -m unittest tests.test_reyva_backend
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BROWSER = Path(__file__).resolve().parents[1] / "reyos-packages/reyos-browser/files/usr/share/reyos/browser"
HOME = Path(tempfile.mkdtemp(prefix="reyva-test-home-"))
os.environ["HOME"] = str(HOME)
os.environ["XDG_DATA_HOME"] = str(HOME / ".local" / "share")
sys.path.insert(0, str(BROWSER))
try:
    import main  # noqa: E402
except ImportError as error:  # no PySide6 here
    main = None
    IMPORT_ERROR = error


class FakeVault:
    def __init__(self):
        self.items = {}

    def save_credential(self, origin, username, password):
        self.items[(origin, username)] = password

    def get_credentials(self, origin):
        return [{"origin": o, "username": u, "password": p} for (o, u), p in sorted(self.items.items()) if o == origin]

    def delete_credential(self, origin, username):
        self.items.pop((origin, username), None)

    def list_all_origins(self):
        return sorted({o for o, _ in self.items})


@unittest.skipIf(main is None, "PySide6 not available")
class Backend(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(HOME / ".local", ignore_errors=True)
        main.BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        self.vault = FakeVault()
        self.backend = main.BrowserBackend(main.ShieldsInterceptor(set()), self.vault, "")
        self.files = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.files, ignore_errors=True)

    # ---- bookmarks
    def test_chrome_style_export_with_folders(self):
        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p>
          <DT><H3 PERSONAL_TOOLBAR_FOLDER="true">Bookmarks bar</H3><DL><p>
            <DT><A HREF="https://a.com/">A</A>
            <DT><H3>Gaming</H3><DL><p><DT><A HREF="https://g.com/">G</A>
              <DT><H3>Retro</H3><DL><p><DT><A HREF="https://r.com/">R &amp; R</A></DL><p>
            </DL><p>
          </DL><p>
          <DT><H3>Other bookmarks</H3><DL><p><DT><A HREF="https://o.com/">O</A></DL><p>
          <DT><A HREF="javascript:alert(1)">bad</A><DT><A HREF="file:///etc/passwd">bad2</A>
        </DL>"""
        path = self.files / "b.html"
        path.write_text(html)
        results = []
        self.backend.bookmarkImportFinished.connect(lambda n, m: results.append((n, m)))
        self.backend.importBookmarks(str(path))
        marks = {b["url"]: b for b in self.backend.bookmarks}
        self.assertEqual(set(marks), {"https://a.com/", "https://g.com/", "https://r.com/", "https://o.com/"})
        self.assertEqual(marks["https://a.com/"]["folder"], "")
        self.assertEqual(marks["https://g.com/"]["folder"], "Gaming")
        self.assertEqual(marks["https://r.com/"]["folder"], "Gaming/Retro")
        self.assertEqual(marks["https://r.com/"]["title"], "R & R")
        self.assertEqual(marks["https://o.com/"]["folder"], "")
        self.assertEqual(results[-1][0], 4)
        # Importing again adds nothing.
        self.backend.importBookmarks(str(path))
        self.assertEqual(len(self.backend.bookmarks), 4)
        self.assertEqual(results[-1], (0, "No new bookmarks or folders found."))

    def test_malformed_and_oversized_bookmark_files(self):
        broken = self.files / "broken.html"
        broken.write_text("<DL><DT><A HREF='https://x.com/'>unclosed <DT><H3>F</H3><DL><A HREF=https://y.com/>y")
        self.backend.importBookmarks(str(broken))
        self.assertEqual(sorted(b["url"] for b in self.backend.bookmarks), ["https://x.com/", "https://y.com/"])
        big = self.files / "big.html"
        big.write_bytes(b" " * (5 * 1024 * 1024 + 1))
        results = []
        self.backend.bookmarkImportFinished.connect(lambda n, m: results.append((n, m)))
        self.backend.importBookmarks(str(big))
        self.assertEqual(results[-1][0], 0)
        self.assertIn("too large", results[-1][1])
        self.backend.importBookmarks(str(self.files / "missing.html"))
        self.assertIn("Could not import", results[-1][1])

    # ---- passwords
    def test_password_csv_variants(self):
        csv_path = self.files / "p.csv"
        csv_path.write_text("name,url,username,password,note\n"
                            "A,https://a.com/login,alice,pw1,\n"
                            "B,b.org,bob,pw2,\n"
                            "C,javascript:x,eve,pw3,\n"
                            "D,https://d.com,,pw4,\n"
                            "A again,https://a.com/other,alice,pw1,\n", encoding="utf-8-sig")
        results = []
        self.backend.passwordImportFinished.connect(lambda n, m: results.append((n, m)))
        self.backend.importPasswords(str(csv_path))
        self.assertEqual(self.vault.items, {("https://a.com", "alice"): "pw1", ("https://b.org", "bob"): "pw2"})
        self.assertEqual(results[-1], (2, "Imported 2 passwords, skipped 3 rows."))

    def test_password_csv_rejected(self):
        results = []
        self.backend.passwordImportFinished.connect(lambda n, m: results.append((n, m)))
        for name, text in {"nourl.csv": "username,password\na,b\n", "empty.csv": "",
                           "nopw.csv": "url,username\nhttps://a.com,a\n"}.items():
            path = self.files / name
            path.write_text(text)
            self.backend.importPasswords(str(path))
            self.assertEqual(results[-1][0], 0, name)
        self.assertEqual(self.vault.items, {})

    # ---- addresses
    def test_origins_and_shortcuts(self):
        self.assertEqual(main.normalize_origin("HTTPS://Example.COM:443/path?q"), "https://example.com")
        self.assertEqual(main.normalize_origin("http://a.com:8080/"), "http://a.com:8080")
        for bad in ["javascript:alert(1)", "file:///etc", "ftp://a.com", "", "https://"]:
            self.assertEqual(main.normalize_origin(bad), "", bad)
        self.assertEqual(main.normalize_shortcut_url("github.com"), "https://github.com")
        for bad in ["not a url", "javascript:alert(1)", "intranet", "data:text/html,x"]:
            self.assertEqual(main.normalize_shortcut_url(bad), "", bad)

    def test_tracking_parameters(self):
        cleaned = main._strip_tracking_params(main.QUrl("https://a.com/p?utm_source=x&id=5&fbclid=y"))
        self.assertEqual(cleaned.toString(), "https://a.com/p?id=5")
        self.assertIsNone(main._strip_tracking_params(main.QUrl("https://a.com/p?id=5")))

    # ---- settings
    def test_settings_survive_damage_and_wrong_types(self):
        main.SETTINGS_PATH.write_text("{broken")
        self.assertTrue(main.load_setting("lowMemoryMode", True))
        main.save_setting("lowMemoryMode", False)
        self.assertFalse(main.load_setting("lowMemoryMode", True))
        main.SETTINGS_PATH.write_text(json.dumps({"lowMemoryMode": "yes", "searchEngine": "Evil"}))
        self.assertTrue(main.load_setting("lowMemoryMode", True))
        self.assertEqual(main.load_setting("searchEngine", "DuckDuckGo", {"DuckDuckGo", "Startpage"}), "DuckDuckGo")
        main.save_setting("x", 1)
        self.assertEqual(oct(main.SETTINGS_PATH.stat().st_mode & 0o777), "0o600")
        self.assertFalse(list(main.SETTINGS_PATH.parent.glob("*.tmp")))

    def test_welcome_only_for_new_profiles(self):
        shutil.rmtree(main.BROWSER_STATE_DIR)
        fresh = main.BrowserBackend(main.ShieldsInterceptor(set()), FakeVault(), "")
        self.assertFalse(fresh.onboardingCompleted)
        shutil.rmtree(main.BROWSER_STATE_DIR, ignore_errors=True)
        main.BROWSER_STATE_DIR.mkdir(parents=True)
        (main.BROWSER_STATE_DIR / "shields-stats.json").write_text('{"lifetimeBlocked": 3}')
        upgraded = main.BrowserBackend(main.ShieldsInterceptor(set()), FakeVault(), "")
        self.assertTrue(upgraded.onboardingCompleted)
        self.assertTrue(main.load_setting("onboardingCompleted", False))

    # ---- web apps
    def write_launcher(self, app_id, exec_line, name="Mail", icon=""):
        folder = main.WEBAPPS_DESKTOP_DIR
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{app_id}.desktop").write_text(f"[Desktop Entry]\nType=Application\nName={name}\nComment=c\nIcon={icon}\nExec={exec_line}\n")
        self.backend.refreshWebApps()

    @unittest.skipIf(main is not None and (main.IS_FLATPAK or main.IS_WINDOWS), "native Linux launcher layout")
    def test_launch_uses_only_address_title_icon(self):
        icon = self.files / "my icon #1.png"
        icon.write_bytes(b"png")
        self.write_launcher("reyos-webapp-mail-1234abcd",
                            '"sh" "-c" "touch /tmp/pwned" "--app-url=https://mail.example.com/u/0" "--app-title=Mail" '
                            + main.reyva_core.quote_desktop_exec_arg(f"--app-icon={icon}"), icon=str(icon))
        apps = self.backend.installedWebApps
        self.assertEqual(apps[0]["iconUrl"], main.QUrl.fromLocalFile(str(icon)).toString())
        self.assertIn("%23", apps[0]["iconUrl"])
        with mock.patch.object(main.subprocess, "Popen") as popen:
            self.assertTrue(self.backend.launchInstalledWebApp("reyos-webapp-mail-1234abcd"))
        command = popen.call_args[0][0]
        self.assertEqual(command[:2], [sys.executable, str((BROWSER / "main.py").resolve())])
        self.assertEqual(command[2:], ["--app-url=https://mail.example.com/u/0", "--app-title=Mail", f"--app-icon={icon}"])

    @unittest.skipIf(main is not None and (main.IS_FLATPAK or main.IS_WINDOWS), "native Linux launcher layout")
    def test_launch_refuses_bad_ids_and_damaged_launchers(self):
        notes = []
        self.backend.notify = lambda title, message: notes.append(title)
        with mock.patch.object(main.subprocess, "Popen") as popen:
            for bad in ["../../bin/sh", "reyos-webapp-x;ls", "", "reyos-webapp-UPPER"]:
                self.assertFalse(self.backend.launchInstalledWebApp(bad))
            self.assertFalse(self.backend.launchInstalledWebApp("reyos-webapp-gone-11111111"))
            self.write_launcher("reyos-webapp-bad-22222222", '"reyos-browser" "--app-url=file:///etc/passwd"')
            self.assertFalse(self.backend.launchInstalledWebApp("reyos-webapp-bad-22222222"))
            popen.assert_not_called()
        self.assertEqual(notes, ["Can't open the app", "Can't open the app"])

    def test_dashboard_through_backend(self):
        self.backend.addBookmark("https://wiki.archlinux.org/", "Arch Wiki")
        results = self.backend.dashboardResults("arch", [{"index": 1, "title": "Arch Linux", "url": "https://archlinux.org/"}], "all")
        self.assertEqual([r["kind"] for r in results], ["tab", "bookmark"])

    # ---- crash recovery
    def test_recovery_off_by_default_and_off_deletes(self):
        self.assertFalse(self.backend.crashRecovery)
        self.backend.saveSession([{"url": "https://a.com", "title": "A"}], 0)
        self.assertFalse((main.BROWSER_STATE_DIR / "recovery").exists() and any((main.BROWSER_STATE_DIR / "recovery").glob("*.json")))
        self.backend.toggleCrashRecovery()
        self.backend.saveSession([{"url": "https://a.com", "title": "A"}], 0)
        self.assertTrue(any((main.BROWSER_STATE_DIR / "recovery").glob("*.json")))
        self.backend.toggleCrashRecovery()
        self.assertEqual(list((main.BROWSER_STATE_DIR / "recovery").glob("*")), [])

    def test_https_fallback_offer(self):
        interceptor = self.backend._interceptor
        interceptor.upgraded_hosts.add("old.example.org")
        self.assertTrue(self.backend.httpsUpgradeFailed("https://old.example.org/page"))
        self.assertFalse(self.backend.httpsUpgradeFailed("https://other.example.org/"))
        self.assertEqual(self.backend.allowInsecureSite("https://old.example.org/page?x=1"), "http://old.example.org/page?x=1")
        self.assertFalse(self.backend.httpsUpgradeFailed("https://old.example.org/page"))
        self.assertFalse(main.reyva_core.should_upgrade_to_https("old.example.org", interceptor.http_allowed_hosts))


    # ---- Shields automatic update (0.1.14)
    def test_shields_auto_update_on_by_default_and_only_when_due(self):
        self.assertTrue(self.backend.shieldsAutoUpdate)
        calls = []
        self.backend.updateShieldsFilterList = lambda: calls.append(1)
        # New install: no downloaded list yet.
        self.backend._check_shields_auto_update()
        self.assertEqual(len(calls), 1)
        # A list downloaded an hour ago: nothing to do.
        main.SHIELDS_CACHE_PATH.write_text("ads.example\n")
        from datetime import datetime, timedelta, timezone
        self.backend._shields_meta = {"lastUpdated": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
        self.backend._check_shields_auto_update()
        self.assertEqual(len(calls), 1)
        # Eight days old: refresh.
        self.backend._shields_meta = {"lastUpdated": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()}
        self.backend._check_shields_auto_update()
        self.assertEqual(len(calls), 2)
        # Turned off: never, and the choice is saved.
        self.backend.toggleShieldsAutoUpdate()
        self.assertFalse(self.backend.shieldsAutoUpdate)
        self.backend._check_shields_auto_update()
        self.assertEqual(len(calls), 2)
        self.assertFalse(main.load_setting("shieldsAutoUpdate", True))

    def test_shields_update_uses_worker_domains(self):
        worker = main.ShieldsUpdateWorker()
        worker.domains = {"a.example", "b.example"}
        self.backend._shields_update_worker = worker
        self.backend._shields_updating = True
        self.backend._on_shields_update_finished(True, "ok", 2)
        self.assertEqual(self.backend._interceptor.blocked_domains, {"a.example", "b.example"})
        self.assertFalse(self.backend.shieldsUpdating)

    # ---- Flatpak launcher written by Reyva when the portal refuses (0.1.14)
    def flatpak_layout(self):
        state = main.BROWSER_STATE_DIR / "webapps"
        patches = [
            mock.patch.object(main, "IS_FLATPAK", True),
            mock.patch.object(main, "WEBAPPS_ICON_DIR", state),
            mock.patch.object(main, "WEBAPPS_INDEX_PATH", state / "index.json", create=True),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        state.mkdir(parents=True, exist_ok=True)
        return state

    def test_flatpak_file_launcher_round_trip(self):
        state = self.flatpak_layout()
        icon = state / "reyos-webapp-mail-1234abcd.png"
        icon.write_bytes(b"png")
        notes = []
        self.backend.notify = lambda title, message: notes.append(title)
        url = "https://mail.example.com/a%20b?x=$y"
        self.assertTrue(self.backend._install_flatpak_file_webapp("reyos-webapp-mail-1234abcd", url, 'My "Mail"', "https://mail.example.com", str(icon)))
        desktop = main.WEBAPPS_DESKTOP_DIR / "com.reyapps.Reyva.reyos_webapp_mail_1234abcd.desktop"
        text = desktop.read_text()
        self.assertIn(f"Icon={icon}\n", text)
        self.assertIn("StartupWMClass=com.reyapps.Reyva.reyos_webapp_mail_1234abcd\n", text)
        launch = main.reyva_core.parse_webapp_launch(main.reyva_core.desktop_entry_value(text, "Exec"))
        self.assertEqual(launch, {"url": url, "title": 'My "Mail"', "icon": str(icon)})
        self.assertTrue(main.reyva_core.desktop_entry_value(text, "Exec").startswith('"flatpak" "run" "com.reyapps.Reyva" '))
        apps = self.backend.installedWebApps
        self.assertEqual([a["id"] for a in apps], ["reyos-webapp-mail-1234abcd"])
        # Removed from the desktop side: drops out of the list.
        desktop.unlink()
        self.backend.refreshWebApps()
        self.assertEqual(self.backend.installedWebApps, [])
        # Install again, then remove through Reyva: launcher and icon go.
        self.backend._install_flatpak_file_webapp("reyos-webapp-mail-1234abcd", url, "Mail", "https://mail.example.com", str(icon))
        self.assertTrue(self.backend.uninstallWebApp("reyos-webapp-mail-1234abcd"))
        self.assertFalse(desktop.exists())
        self.assertFalse(icon.exists())
        self.assertEqual(self.backend.installedWebApps, [])
        self.assertEqual(notes, ["App installed", "App installed", "App removed"])

    def test_flatpak_bundled_logo_uses_exported_icon_name(self):
        self.flatpak_layout()
        self.backend.notify = lambda title, message: None
        logo = str(main.APP_DIR / "assets" / "reyos-browser-logo.png")
        self.backend._install_flatpak_file_webapp("reyos-webapp-x-11111111", "https://x.example/", "X", "https://x.example", logo)
        text = (main.WEBAPPS_DESKTOP_DIR / "com.reyapps.Reyva.reyos_webapp_x_11111111.desktop").read_text()
        self.assertIn("Icon=com.reyapps.Reyva\n", text)

    def test_portal_icon_refusal_falls_back_to_file(self):
        state = self.flatpak_layout()
        notes = []
        self.backend.notify = lambda title, message: notes.append(title)
        icon = state / "reyos-webapp-y-22222222.png"
        icon.write_bytes(b"png")
        self.backend._pending_portal_installs["reyos-webapp-y-22222222"] = {
            "launcher": "com.reyapps.Reyva.reyos_webapp_y_22222222", "icon": str(icon),
            "comment": "c", "url": "https://y.example/"}
        self.backend._pending_portal_fallback["reyos-webapp-y-22222222"] = ("Y", "https://y.example")
        self.backend._finish_portal_install("reyos-webapp-y-22222222", "", "Dynamic launcher icon failed validation")
        self.assertTrue((main.WEBAPPS_DESKTOP_DIR / "com.reyapps.Reyva.reyos_webapp_y_22222222.desktop").is_file())
        self.assertTrue(icon.exists())
        self.assertEqual(notes, ["App installed"])
        # A portal that never answers (locked up) falls back too.
        self.backend._pending_portal_installs["reyos-webapp-w-44444444"] = {
            "launcher": "com.reyapps.Reyva.reyos_webapp_w_44444444", "icon": "", "comment": "c", "url": "https://w.example/"}
        self.backend._pending_portal_fallback["reyos-webapp-w-44444444"] = ("W", "https://w.example")
        self.backend._finish_portal_install("reyos-webapp-w-44444444", "", "TimeoutError")
        self.assertTrue((main.WEBAPPS_DESKTOP_DIR / "com.reyapps.Reyva.reyos_webapp_w_44444444.desktop").is_file())
        # A cancelled portal dialog writes nothing.
        self.backend._pending_portal_installs["reyos-webapp-z-33333333"] = {
            "launcher": "com.reyapps.Reyva.reyos_webapp_z_33333333", "icon": "", "comment": "c", "url": "https://z.example/"}
        self.backend._pending_portal_fallback["reyos-webapp-z-33333333"] = ("Z", "https://z.example")
        self.backend._finish_portal_install("reyos-webapp-z-33333333", "", "cancelled")
        self.assertFalse((main.WEBAPPS_DESKTOP_DIR / "com.reyapps.Reyva.reyos_webapp_z_33333333.desktop").exists())


    def test_hosts_lines_with_trailing_comments(self):
        text = ("# header\n0.0.0.0 a.example #[tracking]\n0.0.0.0 b.example\t# note\n"
                "127.0.0.1 localhost\n0.0.0.0 c.example\nplain.example\n0.0.0.0 x y z\n")
        self.assertEqual(main._parse_domain_lines(text), {"a.example", "b.example", "c.example", "plain.example"})


if __name__ == "__main__":
    unittest.main()
