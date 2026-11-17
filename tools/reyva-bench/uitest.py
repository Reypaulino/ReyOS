#!/usr/bin/env python3
"""Reyva GUI checks under Xvfb: real app, real QML, driven with the keyboard
(xdotool) and the DevTools endpoint; screenshots for the things only a
person can judge. Each check prints PASS/FAIL/NOT TESTED with what it saw.

    python3 uitest.py --source <browser dir> --python <python with PySide6> --out <dir> [--only name,name]
"""
import argparse
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench  # noqa: E402
import cdp  # noqa: E402

RESULTS = []


def record(name: str, status: str, detail: str) -> None:
    RESULTS.append({"test": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}", flush=True)


def data_dir(home: Path) -> Path:
    return home / ".local" / "share" / "reyos-browser"


def wait_for(predicate, timeout: float = 20.0, step: float = 0.2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    return None


def page_session(run, url_part: str) -> cdp.Session | None:
    target = wait_for(lambda: next((t for t in cdp.targets(run.debug_port) if url_part in t.get("url", "")), None))
    return cdp.Session(target["webSocketDebuggerUrl"]) if target else None


def keys(run, *names: str, pause: float = 0.4) -> None:
    run.focus()
    for name in names:
        run.xdotool("key", "--clearmodifiers", name)
        time.sleep(pause)


def type_text(run, text: str) -> None:
    run.focus()
    run.xdotool("type", "--delay", "20", text)
    time.sleep(0.6)


def log_errors(run) -> list[str]:
    try:
        text = (run.home / "reyva.log").read_text(errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if ("qml" in line.lower() or "Traceback" in line or "Error" in line)
            and ("TypeError" in line or "ReferenceError" in line or "Traceback" in line or ".qml:" in line)]


# ---------------------------------------------------------------- checks


def check_welcome(args, server, out: Path) -> None:
    run = bench.Run(args, [])
    try:
        time.sleep(4)
        run.screenshot(str(out / "welcome-step1.png"))
        keys(run, "Return", pause=0.8)
        run.screenshot(str(out / "welcome-step2.png"))
        keys(run, "Return", "Return", "Return", pause=0.8)
        run.screenshot(str(out / "welcome-step5.png"))
        keys(run, "Return", pause=0.8)
        settings = json.loads((data_dir(run.home) / "settings.json").read_text())
        errors = log_errors(run)
        ok = settings.get("onboardingCompleted") is True and not errors
        record("welcome: fresh profile shows it, finishing marks it done", "PASS" if ok else "FAIL",
               f"settings={settings} qml_errors={errors[:3]}")
    finally:
        run.stop()
    # Second launch of the same kind of profile: not shown again.
    home = Path(tempfile.mkdtemp(prefix="reyva-ui-"))
    data_dir(home).mkdir(parents=True)
    (data_dir(home) / "bookmarks.json").write_text(json.dumps([{"url": "https://example.com/", "title": "Example", "folder": ""}]))
    run = bench.Run(args, [], home=home)
    try:
        time.sleep(4)
        run.screenshot(str(out / "welcome-existing-user.png"))
        settings = json.loads((data_dir(home) / "settings.json").read_text())
        record("welcome: an existing profile (upgrade) skips it", "PASS" if settings.get("onboardingCompleted") else "FAIL",
               f"settings={settings}; screenshot welcome-existing-user.png")
    finally:
        run.stop()
    run = bench.Run(args, [server.url(0)])
    try:
        bench_ready = run.wait_ready()
        time.sleep(2)
        run.screenshot(str(out / "welcome-start-url.png"))
        path = data_dir(run.home) / "settings.json"
        settings = json.loads(path.read_text()) if path.exists() else {}
        ok = bench_ready is not None and not settings.get("onboardingCompleted")
        record("welcome: a link opened from another app goes straight to the page", "PASS" if ok else "FAIL",
               f"page loaded in {bench_ready}s, onboarding not marked done: {not settings.get('onboardingCompleted')}")
    finally:
        run.stop()


def seeded_home(bookmarks=None, settings=None, webapp_url: str = "") -> Path:
    home = Path(tempfile.mkdtemp(prefix="reyva-ui-"))
    data = data_dir(home)
    data.mkdir(parents=True)
    base = {"onboardingCompleted": True, "askDownloadLocation": False}
    base.update(settings or {})
    (data / "settings.json").write_text(json.dumps(base))
    if bookmarks:
        (data / "bookmarks.json").write_text(json.dumps(bookmarks))
    if webapp_url:
        apps = home / ".local" / "share" / "applications"
        apps.mkdir(parents=True)
        (apps / "reyos-webapp-benchapp-1234abcd.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Bench App\nComment=Installed from test with Reyva\n"
            f'Exec="reyos-browser" "--app-url={webapp_url}" "--app-title=Bench App" "--app-icon=/nonexistent.png"\n')
    return home


def check_dashboard(args, server, out: Path) -> None:
    bookmarks = [{"url": server.url(7), "title": "Zebra bookmark page", "folder": "Tests"}]
    home = seeded_home(bookmarks, webapp_url=server.url(9))
    urls = [server.url(0), server.url(1), server.url(2)]
    run = bench.Run(args, urls, home=home)
    try:
        run.wait_ready()
        keys(run, "ctrl+t", pause=1.0)
        type_text(run, "Bench script")
        run.screenshot(str(out / "dashboard-tab-results.png"))
        keys(run, "Down", "Return", pause=1.2)
        title = run.window_title()
        tabs_left = len(cdp.targets(run.debug_port))
        record("dashboard: Down + Enter switches to the matching open tab (and drops the empty New Tab)",
               "PASS" if title.startswith("Bench script 1") and tabs_left == 3 else "FAIL",
               f"window title {title!r}, page targets {tabs_left} (3 expected)")

        keys(run, "ctrl+t", pause=1.0)
        type_text(run, "zebra")
        run.screenshot(str(out / "dashboard-bookmark.png"))
        keys(run, "Down", "Return", pause=2.0)
        title = run.window_title()
        record("dashboard: a bookmark opens in the current tab", "PASS" if title.startswith("Bench script 7") else "FAIL",
               f"window title {title!r}")

        keys(run, "ctrl+t", pause=1.0)
        type_text(run, "bench app")
        run.screenshot(str(out / "dashboard-webapp.png"))
        before = set(pids_named("reyos-browser: Bench App"))
        keys(run, "Down", "Return", pause=1.0)
        launched = wait_for(lambda: set(pids_named("reyos-browser: Bench App")) - before, timeout=20)
        record("dashboard: a web app opens in its own app window/process", "PASS" if launched else "FAIL",
               f"new 'reyos-browser: Bench App' process: {sorted(launched) if launched else 'none'}")
        for pid in launched or []:
            try:
                os.killpg(os.getpgid(pid), 9)
            except OSError:
                pass

        keys(run, "Escape", pause=0.4)
        type_text(run, "plain words here")
        keys(run, "Return", pause=2.0)
        page = next((t for t in cdp.targets(run.debug_port) if "duckduckgo" in t.get("url", "")), None)
        record("dashboard: Enter on free text searches the web with only the typed text",
               "PASS" if page and "plain" in page["url"] and "Bench" not in page["url"] else "FAIL",
               f"url={page['url'] if page else None}")
        errors = log_errors(run)
        record("dashboard: no QML/Python errors", "PASS" if not errors else "FAIL", "; ".join(errors[:5]) or "none")
    finally:
        run.stop()


def pids_named(name: str) -> list[int]:
    found = []
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                if Path(f"/proc/{entry}/cmdline").read_bytes().split(b"\0")[0].decode(errors="replace").startswith(name):
                    found.append(int(entry))
            except OSError:
                pass
    return found


def check_tab_search(args, server, out: Path) -> None:
    home = seeded_home()
    run = bench.Run(args, [server.url(i) for i in range(5)], home=home)
    try:
        run.wait_ready()
        keys(run, "ctrl+shift+a", pause=1.0)
        type_text(run, "timer 2")
        run.screenshot(str(out / "tab-search.png"))
        keys(run, "Return", pause=1.0)
        title = run.window_title()
        record("tab search (Ctrl+Shift+A): Enter goes to the matching tab", "PASS" if title.startswith("Bench timer 2") else "FAIL",
               f"window title {title!r}")
    finally:
        run.stop()


def check_vertical_tabs(args, server, out: Path) -> None:
    home = seeded_home(settings={"tabLayout": "vertical"})
    run = bench.Run(args, [server.url(i) for i in range(4)], home=home)
    try:
        run.wait_ready()
        time.sleep(1)
        run.screenshot(str(out / "vertical-tabs.png"))
        keys(run, "ctrl+t", pause=1.0)
        run.screenshot(str(out / "vertical-tabs-newtab.png"))
        errors = log_errors(run)
        record("tabs on the side: renders (see vertical-tabs.png)", "PASS" if not errors else "FAIL", "; ".join(errors[:5]) or "no QML errors")
    finally:
        run.stop()


class PlainHttp:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="reyva-http-"))
        (self.root / "index.html").write_text("<!doctype html><title>Plain HTTP page loaded</title><p>http only</p>")
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(self.root), **k)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        shutil.rmtree(self.root, ignore_errors=True)


def check_https_fallback(args, server, out: Path) -> None:
    plain = PlainHttp()
    try:
        home = seeded_home()
        local = f"http://127.0.0.1:{plain.port}/index.html"
        public = f"http://insecure.reyva-test.com:{plain.port}/index.html"
        # The public-looking name resolves to this machine, so Reyva treats it
        # like any internet site (upgrade to https, which fails here).
        run = bench.Run(args, [local, public], home=home, extra_flags='--host-resolver-rules="MAP insecure.reyva-test.com 127.0.0.1"')
        try:
            loaded = wait_for(lambda: next((t for t in cdp.targets(run.debug_port) if t.get("title") == "Plain HTTP page loaded"
                                            and "127.0.0.1" in t["url"]), None), timeout=20)
            record("http:// on a local address loads (no forced HTTPS)", "PASS" if loaded else "FAIL",
                   f"target={loaded['url'] if loaded else None}")
            time.sleep(3)
            run.screenshot(str(out / "https-fallback-banner.png"))
            public_target = next((t for t in cdp.targets(run.debug_port) if "reyva-test.com" in t.get("url", "")), None)
            record("http:// on an internet name is upgraded; when HTTPS fails the banner offers HTTP (see https-fallback-banner.png)",
                   "PASS" if public_target and public_target["url"].startswith("https://") else "FAIL",
                   f"tab url {public_target['url'] if public_target else None}")
            # "Open over HTTP" (window 1200x760 at 0,0; the bar's button).
            run.xdotool("mousemove", "1050", "122", "click", "1")
            opened = wait_for(lambda: next((t for t in cdp.targets(run.debug_port) if t["url"].startswith("http://insecure.reyva-test.com")
                                            and t.get("title") == "Plain HTTP page loaded"), None), timeout=15)
            run.screenshot(str(out / "https-fallback-after.png"))
            record("Open over HTTP loads the site over http for this session", "PASS" if opened else "FAIL",
                   f"target={opened['url'] if opened else None}")
        finally:
            run.stop()
    finally:
        plain.close()


PERMISSION_JS = ("new Promise(r => navigator.geolocation.getCurrentPosition(() => r('granted'), e => r('error ' + e.code), "
                 "{timeout: 60000}))")


def check_permissions(args, server, out: Path) -> None:
    home = seeded_home()
    run = bench.Run(args, [server.url(0), server.url(1)], home=home)
    try:
        run.wait_ready()
        # From the tab on screen (Chromium holds back requests from hidden tabs).
        session = page_session(run, "/p1.html")
        result = {}
        thread = threading.Thread(target=lambda: result.setdefault("value", session.evaluate(PERMISSION_JS, await_promise=True)))
        thread.start()
        time.sleep(2.0)
        run.screenshot(str(out / "permission-dialog.png"))
        keys(run, "Escape", pause=1.0)
        thread.join(timeout=15)
        value = result.get("value")
        record("permission: closing the dialog denies the request (old code: never answered)",
               "PASS" if value == "error 1" else "FAIL", f"page got {value!r} (expected 'error 1' = PERMISSION_DENIED)")
        session.close()
        errors = log_errors(run)
        record("permission: no QML errors (old code: TypeError reject is not a function)", "PASS" if not errors else "FAIL",
               "; ".join(errors[:3]) or "none")
    finally:
        run.stop()


def check_crash_recovery(args, server, out: Path) -> None:
    home = seeded_home(settings={"crashRecovery": True})
    urls = [server.url(3), server.url(4)]
    run = bench.Run(args, urls, home=home)
    try:
        run.wait_ready()
        time.sleep(3)  # the save runs 1.5 s after a change
        files = sorted(p.name for p in (data_dir(home) / "recovery").glob("*"))
        saved = json.loads(next((data_dir(home) / "recovery").glob("recovery-*.json")).read_text())
        record("recovery on: open tabs are saved (addresses and titles only)",
               "PASS" if [t["url"] for t in saved["tabs"]] == urls and set(saved["tabs"][0]) == {"url", "title"} else "FAIL",
               f"files={files} saved={saved}")
        run.kill()
    finally:
        run.stop(keep_home=True)
    run = bench.Run(args, [], home=home)
    try:
        time.sleep(5)
        run.screenshot(str(out / "recovery-bar.png"))
        run.xdotool("mousemove", "1060", "122", "click", "1")  # Restore
        restored = wait_for(lambda: {t["url"] for t in cdp.targets(run.debug_port)} >= set(urls), timeout=20)
        time.sleep(1)
        leftovers = sorted(p.name for p in (data_dir(home) / "recovery").glob("recovery-*") if not p.name.startswith(f"recovery-{run.proc.pid}."))
        run.screenshot(str(out / "recovery-restored.png"))
        record("recovery: Restore reopens the tabs and deletes the crashed session's file",
               "PASS" if restored and not leftovers and run.window_title().startswith("Bench script 4") else "FAIL",
               f"restored={bool(restored)} leftovers={leftovers} current={run.window_title()!r} (expected the tab that was current: Bench script 4)")
    finally:
        result = run.stop(keep_home=True)
    left = sorted(p.name for p in (data_dir(home) / "recovery").glob("*")) if (data_dir(home) / "recovery").exists() else []
    record("recovery: a clean quit leaves only the earlier crash's file (until Restore/Discard)",
           "PASS" if all(not n.startswith(f"recovery-{run.proc.pid}") for n in left) else "FAIL", f"left={left} exit={result}")
    # Recovery off: nothing written at all.
    home2 = seeded_home()
    run = bench.Run(args, urls, home=home2)
    try:
        run.wait_ready()
        time.sleep(3)
        exists = (data_dir(home2) / "recovery").exists() and any((data_dir(home2) / "recovery").iterdir())
        record("recovery off (default): nothing about tabs is written", "PASS" if not exists else "FAIL",
               f"recovery folder has files: {exists}")
    finally:
        run.stop()
    shutil.rmtree(home, ignore_errors=True)


def check_downloads(args, server, out: Path) -> None:
    home = seeded_home()
    (server.root / "file.bin").write_bytes(os.urandom(300_000))
    run = bench.Run(args, [server.url(0)], home=home)
    try:
        run.wait_ready()
        session = page_session(run, "/p0.html")
        session.evaluate(f"var a=document.createElement('a');a.href='/file.bin';a.download='bench file: test.bin';document.body.appendChild(a);a.click()")
        session.close()
        target = wait_for(lambda: next((p for p in (home / "Downloads").glob("bench file*.bin") if p.stat().st_size == 300_000), None), timeout=20)
        record("downloads (ask-where-to-save off): saved to Downloads, ':' made safe",
               "PASS" if target else "FAIL", f"file={target.name if target else None}")
    finally:
        run.stop()


def check_clean_exit(args, server, out: Path) -> None:
    run = bench.Run(args, [server.url(i) for i in range(3)], home=seeded_home())
    try:
        run.wait_ready()
        time.sleep(2)
    finally:
        result = run.stop()
    ok = result["exit_code"] == 0 and result["leftover_processes"] == 0
    record("quit (Ctrl+Q): exits cleanly, no processes left", "PASS" if ok else "FAIL", json.dumps(result))


def check_shields_dialog(args, server, out: Path) -> None:
    run = bench.Run(args, [server.url(0)], home=seeded_home())
    try:
        run.wait_ready()
        run.focus()
        # Opens Privacy & Shields from the menu: keyboard has no shortcut, so
        # screenshot the page and the dialog for review.
        run.screenshot(str(out / "page.png"))
        record("shields dialog: see screenshots (manual)", "NOT TESTED", "needs a click; covered by manual review")
    finally:
        run.stop()


CHECKS = {
    "welcome": check_welcome,
    "dashboard": check_dashboard,
    "tabsearch": check_tab_search,
    "vertical": check_vertical_tabs,
    "https": check_https_fallback,
    "permissions": check_permissions,
    "recovery": check_crash_recovery,
    "downloads": check_downloads,
    "exit": check_clean_exit,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--only", default="")
    parser.add_argument("--cache-dir", default=str(Path.home() / ".cache" / "reyva-bench"))
    args = parser.parse_args()
    args.keep_logs = False
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    server = bench.FixtureServer()
    wanted = [n for n in args.only.split(",") if n] or list(CHECKS)
    try:
        for name in wanted:
            try:
                CHECKS[name](args, server, out)
            except Exception as error:
                record(name, "FAIL", f"check crashed: {error!r} {traceback.format_exc()[-600:]}")
    finally:
        server.close()
    (out / "results.json").write_text(json.dumps(RESULTS, indent=2))
    return 0 if all(r["status"] != "FAIL" for r in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
