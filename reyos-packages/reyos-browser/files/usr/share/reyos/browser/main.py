#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from PySide6.QtCore import QObject, Property, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineQuick import QQuickWebEngineProfile, QtWebEngineQuick

APP_DIR = Path(__file__).resolve().parent

# StevenBlack's unified hosts list: actively maintained, MIT-licensed,
# merges several well-known ad/tracking/malware blocklists into one file.
# Picked over bundling a single static snapshot forever (the old v1
# behavior) so Shields' domain coverage doesn't silently go stale --
# still an explicit, user-triggered fetch, never automatic/background, to
# keep with the "nothing happens without you asking" design elsewhere in
# this browser.
SHIELDS_LIST_URL = "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"
SHIELDS_STATE_DIR = Path.home() / ".local" / "share" / "reyos-browser"
SHIELDS_CACHE_PATH = SHIELDS_STATE_DIR / "shields-blocklist-cache.txt"
SHIELDS_META_PATH = SHIELDS_STATE_DIR / "shields-meta.json"
_HOSTS_LINE_RE = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1)\s+([a-z0-9.-]+)\s*$", re.IGNORECASE)


class BookmarkImportParser(HTMLParser):
    """Read standard Netscape bookmark-export HTML without executing it."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href", "")
            self._text = []

    def handle_data(self, data) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag) -> None:
        if tag.lower() == "a" and self._href:
            self.entries.append((self._href, "".join(self._text).strip()))
            self._href = ""
            self._text = []


class ShieldsInterceptor(QWebEngineUrlRequestInterceptor):
    blocked = Signal(str)
    def __init__(self, blocked_domains: set[str]) -> None:
        super().__init__()
        self.blocked_domains = blocked_domains
        self.enabled = True
        self._disabled_first_party_hosts: set[str] = set()

    def site_enabled(self, host: str) -> bool:
        return host not in self._disabled_first_party_hosts

    def toggle_site(self, host: str) -> None:
        if host in self._disabled_first_party_hosts:
            self._disabled_first_party_hosts.remove(host)
        else:
            self._disabled_first_party_hosts.add(host)


    def interceptRequest(self, info) -> None:
        first_party = info.firstPartyUrl().host().lower().rstrip(".")
        if not self.enabled or not self.site_enabled(first_party):
            return
        host = info.requestUrl().host().lower().rstrip(".")
        if any(host == domain or host.endswith("." + domain) for domain in self.blocked_domains):
            info.block(True)
            self.blocked.emit(first_party)


class BrowserBackend(QObject):
    shieldsChanged = Signal()
    lowMemoryChanged = Signal()
    blockedRequestCountChanged = Signal()
    currentSiteChanged = Signal()
    currentSiteShieldsChanged = Signal()
    searchEngineChanged = Signal()
    bookmarksChanged = Signal()
    bookmarkImportFinished = Signal(int, str)
    shieldsUpdateFinished = Signal(bool, str)
    shieldsListInfoChanged = Signal()

    def __init__(self, interceptor: ShieldsInterceptor) -> None:
        super().__init__()
        self._interceptor = interceptor
        self._low_memory_mode = True
        self._blocked_request_count = 0
        self._current_site = ""
        self._search_engine = "DuckDuckGo"
        self._bookmarks_path = Path.home() / ".local" / "share" / "reyos-browser" / "bookmarks.json"
        self._bookmarks = self._load_bookmarks()
        interceptor.blocked.connect(self._record_blocked)
        self._shields_update_worker = None
        self._shields_updating = False
        self._shields_meta = load_shields_meta()

    @Property(bool, notify=shieldsListInfoChanged)
    def shieldsUpdating(self) -> bool:
        return self._shields_updating

    @Property(str, notify=shieldsListInfoChanged)
    def shieldsLastUpdated(self) -> str:
        raw = self._shields_meta.get("lastUpdated")
        if not raw:
            return "Never (using the built-in list bundled with ReyOS Browser)"
        try:
            when = datetime.fromisoformat(raw)
            return when.astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return raw

    @Property(int, notify=shieldsListInfoChanged)
    def shieldsDomainCount(self) -> int:
        count = self._shields_meta.get("domainCount")
        return count if isinstance(count, int) else len(self._interceptor.blocked_domains)

    @Slot()
    def updateShieldsFilterList(self) -> None:
        if self._shields_updating:
            return
        self._shields_updating = True
        self.shieldsListInfoChanged.emit()
        self._shields_update_worker = ShieldsUpdateWorker()
        self._shields_update_worker.finished_ok.connect(self._on_shields_update_finished)
        self._shields_update_worker.start()

    @Slot(bool, str, int)
    def _on_shields_update_finished(self, ok: bool, message: str, domain_count: int) -> None:
        self._shields_updating = False
        if ok:
            self._interceptor.blocked_domains = _parse_domain_lines(SHIELDS_CACHE_PATH.read_text(encoding="utf-8"))
            self._shields_meta = load_shields_meta()
        self.shieldsListInfoChanged.emit()
        self.shieldsUpdateFinished.emit(ok, message)

    def _load_bookmarks(self) -> list[dict]:
        try:
            data = json.loads(self._bookmarks_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [entry for entry in data if isinstance(entry, dict) and isinstance(entry.get("url"), str)]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save_bookmarks(self) -> None:
        self._bookmarks_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp_path = self._bookmarks_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(self._bookmarks, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, self._bookmarks_path)

    @Property("QVariantList", notify=bookmarksChanged)
    def bookmarks(self):
        return self._bookmarks

    @Property(int, notify=bookmarksChanged)
    def bookmarksVersion(self) -> int:
        return len(self._bookmarks)

    @Slot(str, result=bool)
    def isBookmarked(self, url: str) -> bool:
        return any(item.get("url") == url for item in self._bookmarks)

    @Slot(str, str)
    def addBookmark(self, url: str, title: str) -> None:
        parsed = QUrl(url)
        if parsed.scheme() not in {"http", "https"} or not parsed.host() or self.isBookmarked(url):
            return
        self._bookmarks.append({"url": url, "title": (title or parsed.host()).strip()[:240]})
        self._save_bookmarks()
        self.bookmarksChanged.emit()

    @Slot(str)
    def removeBookmark(self, url: str) -> None:
        updated = [item for item in self._bookmarks if item.get("url") != url]
        if len(updated) == len(self._bookmarks):
            return
        self._bookmarks = updated
        self._save_bookmarks()
        self.bookmarksChanged.emit()

    @Slot()
    def chooseBookmarkImport(self) -> None:
        result = subprocess.run(["kdialog", "--getopenfilename", str(Path.home()), "Bookmark HTML (*.html *.htm)"], capture_output=True, text=True)
        path = result.stdout.strip()
        if path:
            self.importBookmarks(path)

    @Slot(str)
    def importBookmarks(self, path: str) -> None:
        try:
            bookmark_file = Path(path)
            if bookmark_file.stat().st_size > 5 * 1024 * 1024:
                raise ValueError("The bookmark file is too large.")
            parser = BookmarkImportParser()
            parser.feed(bookmark_file.read_text(encoding="utf-8", errors="replace"))
            existing = {item.get("url") for item in self._bookmarks}
            added = 0
            for url, title in parser.entries:
                parsed = QUrl(url)
                if parsed.scheme() not in {"http", "https"} or not parsed.host() or url in existing:
                    continue
                self._bookmarks.append({"url": url, "title": (title or parsed.host()).strip()[:240]})
                existing.add(url)
                added += 1
            if added:
                self._save_bookmarks()
                self.bookmarksChanged.emit()
            self.bookmarkImportFinished.emit(added, "Imported {} bookmark{}.".format(added, "s" if added != 1 else ""))
        except (OSError, ValueError) as error:
            self.bookmarkImportFinished.emit(0, f"Could not import bookmarks: {error}")

    @Property(bool, notify=shieldsChanged)
    def shieldsEnabled(self) -> bool:
        return self._interceptor.enabled

    @Slot()
    def toggleShields(self) -> None:
        self._interceptor.enabled = not self._interceptor.enabled
        self.shieldsChanged.emit()

    @Property(int, notify=blockedRequestCountChanged)
    def blockedRequestCount(self) -> int:
        return self._blocked_request_count

    @Property(str, notify=currentSiteChanged)
    def currentSite(self) -> str:
        return self._current_site

    @Property(bool, notify=currentSiteShieldsChanged)
    def currentSiteShieldsEnabled(self) -> bool:
        return bool(self._current_site) and self._interceptor.site_enabled(self._current_site)

    @Slot(str)
    def setCurrentSite(self, url: str) -> None:
        host = QUrl(url).host().lower().rstrip(".")
        if host != self._current_site:
            self._current_site = host
            self.currentSiteChanged.emit()
            self.currentSiteShieldsChanged.emit()

    @Slot()
    def toggleCurrentSiteShields(self) -> None:
        if not self._current_site:
            return
        self._interceptor.toggle_site(self._current_site)
        self.currentSiteShieldsChanged.emit()

    @Slot(str)
    def _record_blocked(self, first_party: str) -> None:
        self._blocked_request_count += 1
        self.blockedRequestCountChanged.emit()
    @Property(str, notify=searchEngineChanged)
    def searchEngine(self) -> str:
        return self._search_engine

    @Property(str, notify=searchEngineChanged)
    def searchBase(self) -> str:
        return "https://duckduckgo.com/?q=" if self._search_engine == "DuckDuckGo" else "https://www.startpage.com/do/dsearch?query="

    @Slot(str)
    def setSearchEngine(self, engine: str) -> None:
        if engine in {"DuckDuckGo", "Startpage"} and engine != self._search_engine:
            self._search_engine = engine
            self.searchEngineChanged.emit()
    @Property(bool, notify=lowMemoryChanged)
    def lowMemoryMode(self) -> bool:
        return self._low_memory_mode

    @Slot()
    def toggleLowMemoryMode(self) -> None:
        self._low_memory_mode = not self._low_memory_mode
        self.lowMemoryChanged.emit()

    @Slot(str, str)
    def notify(self, title: str, message: str) -> None:
        """Send a KDE notification without retaining session data."""
        subprocess.Popen(
            ["notify-send", "-a", "ReyOS Browser", "-i", "reyos-browser", title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _parse_domain_lines(text: str) -> set[str]:
    domains = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hosts_match = _HOSTS_LINE_RE.match(line)
        domain = hosts_match.group(1) if hosts_match else line
        domain = domain.lower().rstrip(".")
        if domain and domain not in ("localhost", "localhost.localdomain", "local", "broadcasthost"):
            domains.add(domain)
    return domains


def load_blocked_domains() -> set[str]:
    # Prefer a previously-fetched maintained list over the bundled
    # snapshot -- the bundled shields-blocklist.txt is only the
    # fallback for a fresh install that hasn't run an update yet.
    if SHIELDS_CACHE_PATH.exists():
        try:
            domains = _parse_domain_lines(SHIELDS_CACHE_PATH.read_text(encoding="utf-8", errors="replace"))
            if domains:
                return domains
        except OSError:
            pass
    blocklist = APP_DIR / "shields-blocklist.txt"
    return {line.strip().lower() for line in blocklist.read_text().splitlines() if line and not line.startswith("#")}


def load_shields_meta() -> dict:
    try:
        return json.loads(SHIELDS_META_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


class ShieldsUpdateWorker(QThread):
    finished_ok = Signal(bool, str, int)

    def run(self) -> None:
        try:
            request = urllib.request.Request(SHIELDS_LIST_URL, headers={"User-Agent": "ReyOS-Browser-Shields"})
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            self.finished_ok.emit(False, f"Could not reach the filter list server: {error}", 0)
            return

        domains = _parse_domain_lines(raw)
        if len(domains) < 1000:
            # A genuine fetch of this list is tens of thousands of
            # domains -- a short/empty result means something upstream
            # broke (redirect to an HTML error page, truncated
            # response, wrong URL), not a real, safe-to-use list.
            self.finished_ok.emit(False, "The downloaded filter list looked incomplete or invalid -- kept the previous list.", 0)
            return

        try:
            SHIELDS_STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
            temp_path = SHIELDS_CACHE_PATH.with_suffix(".tmp")
            temp_path.write_text("\n".join(sorted(domains)) + "\n", encoding="utf-8")
            os.replace(temp_path, SHIELDS_CACHE_PATH)
            meta = {
                "source": SHIELDS_LIST_URL,
                "lastUpdated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "domainCount": len(domains),
            }
            SHIELDS_META_PATH.write_text(json.dumps(meta), encoding="utf-8")
        except OSError as error:
            self.finished_ok.emit(False, f"Downloaded the list but could not save it: {error}", 0)
            return

        self.finished_ok.emit(True, f"Filter list updated: {len(domains)} domains.", len(domains))


def main():
    QtWebEngineQuick.initialize()
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ReyOS Browser")
    app.setDesktopFileName("reyos-browser")
    app.setOrganizationName("ReyOS")
    engine = QQmlApplicationEngine()
    interceptor = ShieldsInterceptor(load_blocked_domains())
    backend = BrowserBackend(interceptor)
    engine.rootContext().setContextProperty("browserBackend", backend)
    engine.load(QUrl.fromLocalFile(str(APP_DIR / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]
    profile = window.findChild(QQuickWebEngineProfile, "privateProfile")
    if profile is None:
        return 1
    profile.setUrlRequestInterceptor(interceptor)
    window.initializeFirstTab()
    window.setIcon(QIcon.fromTheme("reyos-browser", QIcon(str(APP_DIR / "assets" / "reyos-r-penguin.png"))))
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
