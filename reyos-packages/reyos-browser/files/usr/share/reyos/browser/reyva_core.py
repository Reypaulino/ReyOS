"""Reyva logic that needs no Qt.

Shields host matching, the rule for which hosts get upgraded to HTTPS, the New
Tab dashboard search, the opt-in crash-recovery files and the parsing of
installed web-app launchers. Kept free of PySide6 so tests can run anywhere
(tests/test_reyva_core.py) and main.py stays the only Qt-facing file.
"""
import ipaddress
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

# ---------------------------------------------------------------- Shields


def host_blocked(host: str, domains) -> bool:
    """True when host or one of its parent domains is in `domains`.

    Same rule as before (host == domain or host ends with "." + domain), but
    it looks up each parent domain in the set instead of walking the whole
    list: the filter list Settings downloads has ~150,000 domains, and the old
    loop ran over all of them for every request a page made."""
    host = (host or "").lower().rstrip(".")
    while host:
        if host in domains:
            return True
        dot = host.find(".")
        if dot < 0:
            return False
        host = host[dot + 1:]
    return False


# Names that only exist on a local network: routers, printers, NAS boxes,
# development servers. Browsers that upgrade to HTTPS leave them alone, as
# they rarely have a certificate (Chrome's HTTPS-Upgrades skips them too).
LOCAL_NAME_SUFFIXES = (
    ".local", ".lan", ".home", ".home.arpa", ".internal", ".intranet", ".corp",
    ".localdomain", ".localhost", ".test", ".example", ".invalid",
)


def should_upgrade_to_https(host: str, http_allowed=()) -> bool:
    """Whether an http:// request to `host` is rewritten to https://.

    Not for IP addresses, one-word names (http://router/), local-network
    names, or hosts the user chose to open over HTTP this session."""
    host = (host or "").lower().rstrip(".").strip("[]")
    if not host or host in http_allowed:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    if "." not in host or host == "localhost":
        return False
    return not host.endswith(LOCAL_NAME_SUFFIXES)


# ------------------------------------------------------- New Tab dashboard

DASHBOARD_LIMITS = {"tab": 6, "app": 4, "bookmark": 6}
BROWSE_LIMIT = 60


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^\w]+", (text or "").lower()) if w]


def _display_url(url: str) -> str:
    text = re.sub(r"^[a-z]+://", "", url or "", flags=re.IGNORECASE)
    return re.sub(r"^www\.", "", text).rstrip("/")


def match_score(query: str, title: str, url: str = "") -> int:
    """0 when not every word of the query is found in the title or address;
    otherwise higher for better matches (exact title, title start, start of a
    word, anywhere)."""
    q = (query or "").strip().lower()
    if not q:
        return 0
    title_l = (title or "").lower()
    url_l = _display_url(url).lower()
    haystack = title_l + " " + url_l
    terms = q.split()
    if not all(term in haystack for term in terms):
        return 0
    score = 10
    if title_l == q:
        score += 100
    elif title_l.startswith(q):
        score += 70
    elif q in title_l:
        score += 40
    if url_l.startswith(q):
        score += 60
    title_words = _words(title_l)
    for term in terms:
        if any(word.startswith(term) for word in title_words):
            score += 15
    return score


def dashboard_results(query: str, tabs: list, bookmarks: list, apps: list, kind: str = "all") -> list[dict]:
    """Local matches for the New Tab search box, best first within each kind:
    open tabs, then installed web apps, then bookmarks. Nothing leaves the
    computer; the QML adds the web-search row itself.

    kind narrows it to "tab", "app" or "bookmark"; with one kind picked, an
    empty query lists that kind (up to BROWSE_LIMIT) so it can be browsed.
    "all" with an empty query returns nothing: the page stays sparse until
    someone types."""
    query = (query or "").strip()
    browsing = not query
    if browsing and kind not in DASHBOARD_LIMITS:
        return []

    def limit(which: str) -> int:
        return BROWSE_LIMIT if (browsing or kind == which) else DASHBOARD_LIMITS[which]

    def wanted(which: str) -> bool:
        return kind in ("all", which)

    def score(title: str, url: str) -> int:
        return 1 if browsing else match_score(query, title, url)

    results = []
    if wanted("tab"):
        scored_tabs = []
        for tab in tabs or []:
            try:
                index = int(tab.get("index", -1))
            except (TypeError, ValueError, AttributeError):
                continue
            title, url = str(tab.get("title", "")), str(tab.get("url", ""))
            if index < 0 or not url or tab.get("home"):
                continue
            points = score(title, url)
            if points:
                scored_tabs.append((points, index, {"kind": "tab", "index": index, "title": title or url, "url": url,
                                                     "detail": _display_url(url), "state": str(tab.get("state", ""))}))
        scored_tabs.sort(key=lambda item: (-item[0], item[1]))
        results += [entry for _, _, entry in scored_tabs[:limit("tab")]]

    if wanted("app"):
        scored_apps = []
        for app in apps or []:
            name = str(app.get("name", ""))
            points = score(name, "")
            if points and app.get("id"):
                scored_apps.append((points, name.lower(), {"kind": "app", "id": str(app["id"]), "title": name,
                                                            "detail": str(app.get("comment", "")),
                                                            "icon": str(app.get("iconUrl", ""))}))
        scored_apps.sort(key=lambda item: (-item[0], item[1]))
        results += [entry for _, _, entry in scored_apps[:limit("app")]]

    if wanted("bookmark"):
        open_urls = {str(tab.get("url", "")) for tab in tabs or [] if isinstance(tab, dict)}
        scored_marks = []
        for mark in bookmarks or []:
            url = str(mark.get("url", ""))
            title = str(mark.get("title", "")) or url
            if not url.startswith(("http://", "https://")):
                continue
            points = score(title, url)
            if points:
                folder = str(mark.get("folder", ""))
                detail = _display_url(url) + ("  \u00b7  " + folder if folder else "")
                scored_marks.append((points, title.lower(), {"kind": "bookmark", "title": title, "url": url,
                                                             "detail": detail, "open": url in open_urls}))
        scored_marks.sort(key=lambda item: (-item[0], item[1]))
        results += [entry for _, _, entry in scored_marks[:limit("bookmark")]]
    return results


# ------------------------------------------------------- crash recovery

RECOVERY_VERSION = 1
RECOVERY_MAX_TABS = 200
RECOVERY_MAX_URL = 4096


def clean_recovery_tabs(tabs) -> list[dict]:
    """Only what's needed to reopen a tab: an http(s) address and its title.
    Never page contents, form data, cookies or passwords."""
    cleaned = []
    for tab in tabs or []:
        if not isinstance(tab, dict):
            continue
        url = str(tab.get("url", ""))
        if len(url) > RECOVERY_MAX_URL or urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
            continue
        cleaned.append({"url": url, "title": str(tab.get("title", ""))[:300]})
        if len(cleaned) >= RECOVERY_MAX_TABS:
            break
    return cleaned


def _lock(handle) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


class RecoveryStore:
    """Opt-in crash recovery.

    Each running Reyva window process owns recovery-<pid>.json plus a
    recovery-<pid>.lock it keeps locked while it runs. A clean exit deletes
    both. At start-up, a .lock that can be locked belongs to a process that
    is gone without cleaning up: a crash, a killed process or a power cut.
    Its tabs are offered for restoring once, then deleted either way."""

    def __init__(self, folder: Path, pid: int | None = None) -> None:
        self.folder = Path(folder)
        self.pid = os.getpid() if pid is None else pid
        self.data_path = self.folder / f"recovery-{self.pid}.json"
        self.lock_path = self.folder / f"recovery-{self.pid}.lock"
        self._lock_handle = None

    def start(self) -> bool:
        """Takes this process's lock. False if the folder can't be written."""
        if self._lock_handle is not None:
            return True
        try:
            self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            handle = open(self.lock_path, "a+b")
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            if not _lock(handle):
                handle.close()
                return False
            self._lock_handle = handle
            return True
        except OSError:
            return False

    def save(self, tabs, current: int) -> bool:
        if not self.start():
            return False
        cleaned = clean_recovery_tabs(tabs)
        data = {"version": RECOVERY_VERSION, "saved": int(time.time()), "tabs": cleaned,
                "current": max(0, min(int(current), len(cleaned) - 1)) if cleaned else 0}
        try:
            _write_private(self.data_path, json.dumps(data, ensure_ascii=False))
            return True
        except OSError:
            return False

    def stop(self) -> None:
        """Clean exit, or recovery turned off: nothing of this session stays."""
        for path in (self.data_path, self.data_path.with_name(self.data_path.name + ".tmp")):
            try:
                path.unlink()
            except OSError:
                pass
        if self._lock_handle is not None:
            try:
                self._lock_handle.close()
            except OSError:
                pass
            self._lock_handle = None
        try:
            self.lock_path.unlink()
        except OSError:
            pass

    def _orphans(self) -> list[tuple[Path, Path]]:
        found = []
        if not self.folder.is_dir():
            return found
        for lock_path in sorted(self.folder.glob("recovery-*.lock")):
            if lock_path == self.lock_path:
                continue
            try:
                handle = open(lock_path, "a+b")
            except OSError:
                continue
            try:
                if _lock(handle):
                    found.append((lock_path, lock_path.with_suffix(".json")))
            finally:
                handle.close()
        # A .json whose .lock is gone (e.g. deleted by hand) counts too.
        for data_path in self.folder.glob("recovery-*.json"):
            lock_path = data_path.with_suffix(".lock")
            if data_path != self.data_path and not lock_path.exists():
                found.append((lock_path, data_path))
        return found

    def unclean_sessions(self) -> dict | None:
        """Tabs of every earlier Reyva process that didn't exit cleanly,
        merged in order, or None."""
        tabs, current = [], 0
        for _lock_path, data_path in self._orphans():
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # half-written or damaged: dropped, never a crash
            if not isinstance(data, dict) or data.get("version") != RECOVERY_VERSION:
                continue
            cleaned = clean_recovery_tabs(data.get("tabs"))
            if cleaned and not tabs:
                try:
                    current = max(0, min(int(data.get("current", 0)), len(cleaned) - 1))
                except (TypeError, ValueError):
                    current = 0
            tabs += cleaned
        tabs = tabs[:RECOVERY_MAX_TABS]
        return {"tabs": tabs, "current": current} if tabs else None

    def discard_unclean(self) -> None:
        """Deletes the leftovers of earlier sessions (after Restore or Discard)."""
        for lock_path, data_path in self._orphans():
            for path in (data_path, data_path.with_name(data_path.name + ".tmp"), lock_path):
                try:
                    path.unlink()
                except OSError:
                    pass

    def discard_all(self) -> None:
        """Recovery switched off: this session's file and any leftovers go."""
        self.discard_unclean()
        self.stop()


# ---------------------------------------------------- installed web apps

WEBAPP_ID_RE = re.compile(r"reyos-webapp-[a-z0-9-]{1,80}")


def valid_webapp_id(app_id) -> bool:
    return isinstance(app_id, str) and bool(WEBAPP_ID_RE.fullmatch(app_id))


def quote_desktop_exec_arg(value: str) -> str:
    """One quoted argument for a desktop entry's Exec line.

    Two escaping levels apply (Desktop Entry spec): inside the quotes, \\ " `
    and $ get a backslash; then the whole value is a desktop "string", where
    every backslash is written twice. And a literal % is written %%. Reyva
    used to write one backslash: GIO (Ubuntu) then refused the whole Exec
    line ("Desktop file didn't specify Exec field") for a title with " or $,
    and read %20 in an address as a field code (a%20b opened a0b)."""
    quoted = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return '"' + quoted.replace("\\", "\\\\").replace("%", "%%") + '"'


def _unescape_desktop_string(value: str) -> str:
    """The desktop-entry "string" level: \\s \\n \\t \\r \\\\. Other
    backslashes are left for the Exec quoting level (launchers written by
    older Reyva versions used only one)."""
    return re.sub(r"\\([\\snrt])", lambda m: {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}[m.group(1)], value)


def parse_webapp_launch(exec_line: str) -> dict | None:
    """The --app-url/--app-title/--app-icon values from a web-app launcher's
    Exec line (Reyva's own .desktop file, or the one the DynamicLauncher
    portal stored). Nothing else of the line is used, so a changed launcher
    can't make Reyva run another program. None if there's no usable address."""
    if not exec_line:
        return None
    try:
        parts = shlex.split(_unescape_desktop_string(exec_line))
    except ValueError:
        return None
    values = {}
    for part in parts:
        for key in ("url", "title", "icon"):
            prefix = f"--app-{key}="
            if part.startswith(prefix):
                # Desktop-entry escapes: %% is a literal %, \$ and \` were
                # escaped by Reyva's own writer.
                values[key] = part[len(prefix):].replace("%%", "%").replace("\\$", "$").replace("\\`", "`")
    url = values.get("url", "")
    split = urlsplit(url)
    if split.scheme not in ("http", "https") or not split.hostname or any(c in url for c in "\r\n"):
        return None
    return {"url": url, "title": values.get("title", "")[:80], "icon": values.get("icon", "")}


def desktop_entry_value(text: str, field: str) -> str:
    """A key from a desktop entry's [Desktop Entry] group (not localized)."""
    in_main = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_main = stripped == "[Desktop Entry]"
            continue
        if in_main and line.startswith(field + "="):
            return line[len(field) + 1:]
    return ""


SHIELDS_UPDATE_INTERVAL_DAYS = 7


def shields_update_due(last_updated: str | None, now: float | None = None,
                       days: int = SHIELDS_UPDATE_INTERVAL_DAYS) -> bool:
    """True when the downloaded Shields filter list should be refreshed: never
    downloaded (a new install still on the small built-in list), older than
    `days`, an unreadable date, or a date in the future (clock was wrong)."""
    if not last_updated or not isinstance(last_updated, str):
        return True
    from datetime import datetime, timezone
    try:
        when = datetime.fromisoformat(last_updated)
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    age = (time.time() if now is None else now) - when.timestamp()
    return age < 0 or age >= days * 86400
