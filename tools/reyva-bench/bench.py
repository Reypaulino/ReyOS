#!/usr/bin/env python3
"""Reyva memory / CPU / startup benchmark (Linux, stdlib only).

Runs Reyva from a source folder under its own Xvfb with a throwaway profile,
opens deterministic local test pages, and records for the whole process tree
(the Python/Qt parent plus every QtWebEngineProcess):

  * PSS (from /proc/<pid>/smaps_rollup) and RSS, in MB
  * renderer/helper process count
  * CPU seconds used over an idle window
  * startup time: launch -> every requested page reports its <title> over the
    DevTools endpoint (QTWEBENGINE_REMOTE_DEBUGGING)

Nothing here runs inside Reyva in production; it only reads /proc and the
DevTools /json list. Kill is by process group, never pkill -f (Reyva renames
itself with setproctitle).

    python3 bench.py --source <browser dir> --python <python with PySide6> \
        --scenarios blank,tabs1,tabs5,tabs10,tabs20,churn --reps 3 --out result.json
"""
import argparse
import http.server
import json
import os
import shutil
import signal
import socket
import ssl
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

CLK_TCK = os.sysconf("SC_CLK_TCK")
PAGE_KINDS = ("text", "script", "timer")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fixture_html(kind: str, number: int) -> str:
    """Deterministic pages. text: a long article; script: keeps ~15 MB of JS
    objects alive; timer: updates the DOM every 100 ms (background CPU)."""
    paragraphs = "\n".join(
        f"<p>Paragraph {i} of page {number}. " + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 6) + "</p>"
        for i in range(400)
    )
    css = "".join(f".c{i}{{color:#{(i * 2654435761) & 0xFFFFFF:06x};margin:{i % 7}px}}" for i in range(800))
    script = ""
    if kind == "script":
        script = ("<script>window.keep=[];for(let i=0;i<120000;i++){keep.push({i:i,s:'item-'+i,a:[i,i*2,i*3]})}"
                  "document.title=document.title+' ready';</script>")
    elif kind == "timer":
        script = ("<script>let n=0;setInterval(()=>{document.getElementById('tick').textContent=++n},100);</script>")
    images = ""
    if kind == "heavy":
        # 80 subresources: what a news or shopping page asks for.
        images = "".join(f'<img src="/img/{i}.png?p={number}" width=8 height=8>' for i in range(80))
    return (f"<!doctype html><html><head><meta charset=utf-8><title>Bench {kind} {number}</title>"
            f"<style>{css}</style></head><body>"
            "<script>addEventListener('load',()=>{document.title+=' loaded'})</script>"
            f"<h1>Bench page {number} ({kind})</h1><div id=tick>0</div>"
            f"{images}{paragraphs}{script}</body></html>")


def tiny_png() -> bytes:
    import struct
    import zlib
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + b"\xc9\x79\x32" * 8 for _ in range(8))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FixtureServer:
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="reyva-bench-pages-"))
        for number in range(40):
            kind = PAGE_KINDS[number % len(PAGE_KINDS)]
            (self.root / f"p{number}.html").write_text(fixture_html(kind, number), encoding="utf-8")
            (self.root / f"h{number}.html").write_text(fixture_html("heavy", number), encoding="utf-8")
        (self.root / "img").mkdir()
        for i in range(80):
            (self.root / "img" / f"{i}.png").write_bytes(tiny_png())
        handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(self.root), **k)
        http.server.SimpleHTTPRequestHandler.log_message = lambda *a, **k: None
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        # HTTPS: Reyva upgrades every http:// request (Shields), so plain
        # http fixtures would never load. Self-signed; the run passes
        # --ignore-certificate-errors to Chromium (benchmark only).
        cert = self.root / "cert.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(cert), "-out", str(cert),
                        "-days", "2", "-subj", "/CN=127.0.0.1"], check=True, capture_output=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert))
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self, number: int, kind: str = "p") -> str:
        return f"https://127.0.0.1:{self.port}/{kind}{number}.html"

    def close(self) -> None:
        self.server.shutdown()
        shutil.rmtree(self.root, ignore_errors=True)


def children_map() -> dict[int, list[int]]:
    result: dict[int, list[int]] = {}
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry}/stat").read_text()
        except OSError:
            continue
        ppid = int(stat.rsplit(")", 1)[1].split()[1])
        result.setdefault(ppid, []).append(int(entry))
    return result


def process_tree(root: int) -> list[int]:
    kids = children_map()
    seen, stack = [], [root]
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.append(pid)
        stack.extend(kids.get(pid, []))
    return seen


def memory_of(pid: int) -> tuple[int, int]:
    """(PSS kB, RSS kB) of one process; zeros if it's gone."""
    pss = rss = 0
    try:
        for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
            if line.startswith("Pss:"):
                pss = int(line.split()[1])
            elif line.startswith("Rss:"):
                rss = int(line.split()[1])
    except OSError:
        pass
    return pss, rss


def cpu_ticks(pid: int) -> int:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(fields[11]) + int(fields[12])  # utime + stime
    except (OSError, IndexError, ValueError):
        return 0


def comm(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text().strip()
    except OSError:
        return ""


def snapshot(root: int, xvfb: int) -> dict:
    pids = [pid for pid in process_tree(root) if pid != xvfb]
    total_pss = total_rss = 0
    helpers = 0
    by_name: dict[str, int] = {}
    for pid in pids:
        pss, rss = memory_of(pid)
        total_pss += pss
        total_rss += rss
        name = comm(pid)
        by_name[name] = by_name.get(name, 0) + pss
        if "QtWebEngine" in name:
            helpers += 1
    return {"pss_mb": round(total_pss / 1024, 1), "rss_mb": round(total_rss / 1024, 1),
            "processes": len(pids), "webengine_processes": helpers,
            "pss_by_name_mb": {k: round(v / 1024, 1) for k, v in sorted(by_name.items())}}


def cpu_window(root: int, seconds: float) -> float:
    def total() -> int:
        return sum(cpu_ticks(pid) for pid in process_tree(root))
    start = total()
    time.sleep(seconds)
    return round((total() - start) / CLK_TCK, 2)


def devtools_targets(port: int) -> list[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
            return json.loads(response.read())
    except Exception:
        return []


class Run:
    def __init__(self, args, urls: list[str], settings: dict | None = None, shields_domains: int = 0,
                 home: Path | None = None, extra_flags: str = "") -> None:
        self.args = args
        self.home = Path(home) if home else Path(tempfile.mkdtemp(prefix="reyva-bench-home-"))
        data = self.home / ".local" / "share" / "reyos-browser"
        data.mkdir(parents=True, exist_ok=True)
        (self.home / "Downloads").mkdir(exist_ok=True)
        if settings:
            (data / "settings.json").write_text(json.dumps(settings))
        if shields_domains:
            # The size of the list Settings > Filter list > Update downloads.
            (data / "shields-blocklist-cache.txt").write_text(
                "\n".join(f"tracker{i}.adnet{i % 997}.com" for i in range(shields_domains)) + "\n")
        # -displayfd: Xvfb picks a free display and says which once it's ready.
        read_fd, write_fd = os.pipe()
        self.xvfb = subprocess.Popen(["Xvfb", "-displayfd", str(write_fd), "-screen", "0", "1600x1000x24", "-nolisten", "tcp"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, pass_fds=(write_fd,))
        os.close(write_fd)
        with os.fdopen(read_fd) as pipe:
            self.display = int(pipe.readline().strip())
        self.debug_port = free_port()
        # A clean environment: nothing from the shell that started the
        # benchmark (an IDE sandbox leaks FONTCONFIG_FILE etc.).
        env = {key: os.environ[key] for key in ("PATH", "LANG", "USER", "LOGNAME", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS") if key in os.environ}
        env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
        env.update({
            "QTWEBENGINE_CHROMIUM_FLAGS": ("--ignore-certificate-errors " + extra_flags).strip(),
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_CACHE_HOME": str(Path(args.cache_dir)),
            "DISPLAY": f":{self.display}",
            "QT_QPA_PLATFORM": "xcb",
            "QTWEBENGINE_REMOTE_DEBUGGING": f"127.0.0.1:{self.debug_port}",
        })
        env.pop("WAYLAND_DISPLAY", None)
        self.log = open(self.home / "reyva.log", "w")
        self.started = time.monotonic()
        self.proc = subprocess.Popen([args.python, str(Path(args.source) / "main.py"), *urls], env=env, cwd=str(self.home),
                                     stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        self.urls = urls

    def wait_ready(self, timeout: float = 90.0) -> float | None:
        """Seconds until every requested page (or the New Tab page) has its title."""
        wanted = set(self.urls)
        deadline = self.started + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return None
            targets = [t for t in devtools_targets(self.debug_port) if t.get("type") == "page"]
            if wanted:
                titled = {t["url"] for t in targets if t.get("url") in wanted and "loaded" in (t.get("title") or "")}
                if titled >= wanted:
                    return round(time.monotonic() - self.started, 2)
            elif any(t.get("title") == "New Tab" for t in targets):
                return round(time.monotonic() - self.started, 2)
            time.sleep(0.05)
        return None

    def xdotool(self, *argv: str) -> None:
        subprocess.run(["xdotool", *argv], env=dict(os.environ, DISPLAY=f":{self.display}"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)

    def focus(self) -> None:
        self.xdotool("search", "--onlyvisible", "--name", "Reyva", "windowfocus", "--sync")

    def screenshot(self, path: str) -> None:
        subprocess.run(["import", "-window", "root", path], env=dict(os.environ, DISPLAY=f":{self.display}"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)

    def window_title(self) -> str:
        out = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", "Reyva", "getwindowname"],
                             env=dict(os.environ, DISPLAY=f":{self.display}"), capture_output=True, text=True, timeout=10)
        return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else ""

    def kill(self) -> None:
        """Like a crash: no clean-up runs in Reyva."""
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.proc.wait(timeout=10)

    def stop(self, keep_home: bool = False) -> dict:
        result = {"exit_code": None, "clean_exit_seconds": None, "leftover_processes": 0}
        if self.proc.poll() is None:
            # Ctrl+Q is Reyva's own quit; measure whether every child exits.
            self.focus()
            self.xdotool("key", "--clearmodifiers", "ctrl+q")
            begin = time.monotonic()
            try:
                self.proc.wait(timeout=15)
                result["clean_exit_seconds"] = round(time.monotonic() - begin, 2)
            except subprocess.TimeoutExpired:
                pass
        result["exit_code"] = self.proc.poll()
        time.sleep(1.0)
        try:
            leftover = subprocess.run(["pgrep", "-g", str(self.proc.pid)], capture_output=True, text=True).stdout.split()
        except OSError:
            leftover = []
        result["leftover_processes"] = len(leftover)
        for group in (self.proc.pid, self.xvfb.pid):
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.log.close()
        if self.args.keep_logs:
            result["log"] = (self.home / "reyva.log").read_text(errors="replace")[-4000:]
        if not keep_home:
            shutil.rmtree(self.home, ignore_errors=True)
        return result


def scenario_tabs(args, server: FixtureServer, count: int, settings=None, kind: str = "p", shields_domains: int = 0) -> dict:
    urls = [server.url(i, kind) for i in range(count)] if count else []
    run = Run(args, urls, settings, shields_domains)
    try:
        ready = run.wait_ready()
        time.sleep(args.settle)
        mem = snapshot(run.proc.pid, run.xvfb.pid)
        idle_cpu = cpu_window(run.proc.pid, args.idle)
        return {"ready_seconds": ready, **mem, "idle_cpu_seconds": idle_cpu, "idle_window": args.idle, **run.stop()}
    except BaseException:
        run.stop()
        raise


def scenario_churn(args, server: FixtureServer) -> dict:
    """Open and close a tab 30 times with the keyboard (Ctrl+T, type, Enter, Ctrl+W)."""
    run = Run(args, [server.url(0)])
    try:
        ready = run.wait_ready()
        time.sleep(args.settle)
        before = snapshot(run.proc.pid, run.xvfb.pid)
        run.focus()
        for cycle in range(args.churn):
            run.xdotool("key", "--clearmodifiers", "ctrl+t")
            time.sleep(0.6)
            run.xdotool("type", "--delay", "5", server.url(1 + cycle % 30))
            run.xdotool("key", "Return")
            time.sleep(1.6)
            run.xdotool("key", "--clearmodifiers", "ctrl+w")
            time.sleep(0.6)
        time.sleep(args.settle)
        after = snapshot(run.proc.pid, run.xvfb.pid)
        pages = [t for t in devtools_targets(run.debug_port) if t.get("type") == "page"]
        return {"ready_seconds": ready, "cycles": args.churn, "before_pss_mb": before["pss_mb"], "after_pss_mb": after["pss_mb"],
                "delta_pss_mb": round(after["pss_mb"] - before["pss_mb"], 1), "pages_left": len(pages),
                "webengine_processes_after": after["webengine_processes"], **run.stop()}
    except BaseException:
        run.stop()
        raise


def summarize(values: list[float]) -> dict:
    values = [v for v in values if v is not None]
    if not values:
        return {}
    return {"median": round(statistics.median(values), 2), "min": round(min(values), 2), "max": round(max(values), 2), "n": len(values)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--scenarios", default="blank,tabs1,tabs5,tabs10,tabs20,churn")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--settle", type=float, default=15.0)
    parser.add_argument("--idle", type=float, default=30.0)
    parser.add_argument("--churn", type=int, default=30)
    parser.add_argument("--cache-dir", default=str(Path.home() / ".cache" / "reyva-bench"))
    parser.add_argument("--keep-logs", action="store_true")
    parser.add_argument("--label", default="")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    Path(args.cache_dir).mkdir(parents=True, exist_ok=True)
    # Stopped from outside: still tear down Xvfb and Reyva (Run.stop).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    server = FixtureServer()
    results: dict = {"label": args.label, "source": args.source, "python": args.python,
                     "started": time.strftime("%Y-%m-%d %H:%M:%S"), "machine": machine_info(args.python), "scenarios": {}}
    try:
        # One unmeasured warm-up launch so the first measured run isn't a
        # cold font/shader cache.
        scenario_tabs(args, server, 0)
        for name in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
            runs = []
            for rep in range(args.reps):
                if name == "blank":
                    runs.append(scenario_tabs(args, server, 0))
                elif name.startswith("tabs"):
                    runs.append(scenario_tabs(args, server, int(name[4:])))
                elif name == "lowmem-off10":
                    runs.append(scenario_tabs(args, server, 10, {"lowMemoryMode": False}))
                elif name == "heavy3":
                    runs.append(scenario_tabs(args, server, 3, kind="h"))
                elif name == "heavy3-list150k":
                    runs.append(scenario_tabs(args, server, 3, kind="h", shields_domains=150_000))
                elif name == "churn":
                    runs.append(scenario_churn(args, server))
                print(f"{name} rep {rep + 1}: {json.dumps({k: v for k, v in runs[-1].items() if k not in ('pss_by_name_mb', 'log')})}", flush=True)
            keys = ("ready_seconds", "pss_mb", "rss_mb", "webengine_processes", "idle_cpu_seconds", "clean_exit_seconds",
                    "before_pss_mb", "after_pss_mb", "delta_pss_mb", "leftover_processes")
            summary = {key: summarize([r.get(key) for r in runs]) for key in keys if any(key in r for r in runs)}
            results["scenarios"][name] = {"summary": summary, "runs": runs}
    finally:
        server.close()
    Path(args.out).write_text(json.dumps(results, indent=2) + "\n")
    return 0


def machine_info(python: str) -> dict:
    info = {"kernel": os.uname().release}
    try:
        info["cpu"] = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
        info["ram_gb"] = round(int(next(l.split()[1] for l in open("/proc/meminfo") if l.startswith("MemTotal"))) / 1048576, 1)
        info["distro"] = next((l.split("=", 1)[1].strip().strip('"') for l in open("/etc/os-release") if l.startswith("PRETTY_NAME")), "")
        info["pyside"] = subprocess.run([python, "-c", "import PySide6, PySide6.QtCore as c; print(PySide6.__version__, c.qVersion())"],
                                        capture_output=True, text=True, timeout=30).stdout.strip()
        info["governor"] = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read_text().strip()
    except Exception:
        pass
    return info


if __name__ == "__main__":
    sys.exit(main())
