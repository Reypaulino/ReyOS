#!/usr/bin/env python3
import csv
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"

try:
    import secretstorage
except ModuleNotFoundError:
    secretstorage = None

try:
    import keyring
except ModuleNotFoundError:
    keyring = None

from PySide6.QtCore import QFile, QIODevice, QObject, Property, QThread, QUrl, QUrlQuery, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineQuick import QQuickWebEngineProfile, QtWebEngineQuick
from PySide6.QtWidgets import QApplication, QFileDialog

APP_DIR = Path(__file__).resolve().parent
if IS_WINDOWS:
    BROWSER_STATE_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ReyOS Browser"
else:
    BROWSER_STATE_DIR = Path.home() / ".local" / "share" / "reyos-browser"
PASSWORD_BLOCKLIST_PATH = BROWSER_STATE_DIR / "password-blocklist.json"
PASSWORD_AUTOFILL_SCRIPT_PATH = APP_DIR / "password-autofill.js"
FINGERPRINT_PROTECTION_SCRIPT_PATH = APP_DIR / "fingerprint-protection.js"
QWEBCHANNEL_JS_PATHS = (
    Path("/usr/share/qt6/webchannel/qwebchannel.js"),
    APP_DIR / "qwebchannel.js",
)

# Two actively-maintained, permissively-licensed, plain ad/tracking hosts
# lists -- no opinionated content categories (gambling/social/etc. variants
# some of these projects also offer are deliberately not used here, since
# that would silently change what a user can reach, not just what tracks
# them). StevenBlack's is itself already a merge of several well-known
# lists; Dan Pollock's someonewhocares.org list is added as a second,
# independently-maintained source for coverage that alone might miss.
# Picked over bundling a single static snapshot forever (the old v1
# behavior) so Shields' domain coverage doesn't silently go stale --
# still an explicit, user-triggered fetch, never automatic/background, to
# keep with the "nothing happens without you asking" design elsewhere in
# this browser.
SHIELDS_LIST_URLS = [
    "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
    "https://someonewhocares.org/hosts/zero/hosts",
]
SHIELDS_STATE_DIR = BROWSER_STATE_DIR
SHIELDS_CACHE_PATH = SHIELDS_STATE_DIR / "shields-blocklist-cache.txt"
SHIELDS_META_PATH = SHIELDS_STATE_DIR / "shields-meta.json"
# Lifetime blocked-request total, persisted once per session (on quit, not
# per-block -- writing a file on every single ad/tracker hit would be real
# I/O overhead for no benefit) so something outside this one running
# process -- namely Control Center's Security dashboard -- has a real,
# durable number to show instead of nothing. The in-memory per-session
# count (blockedRequestCount) was never written anywhere before this.
SHIELDS_STATS_PATH = SHIELDS_STATE_DIR / "shields-stats.json"
_HOSTS_LINE_RE = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1)\s+([a-z0-9.-]+)\s*$", re.IGNORECASE)
PASSWORD_IMPORT_MAX_BYTES = 5 * 1024 * 1024
_PASSWORD_CSV_ORIGIN_HEADERS = {"origin", "url", "website", "loginuri", "hostname", "formactionorigin"}
_PASSWORD_CSV_USERNAME_HEADERS = {"username", "usernamevalue", "user", "email", "loginusername"}
_PASSWORD_CSV_PASSWORD_HEADERS = {"password", "passwordvalue", "pass", "loginpassword"}


class BookmarkImportParser(HTMLParser):
    """Read standard Netscape bookmark-export HTML without executing it."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[tuple[str, str, str]] = []
        self._href = ""
        self._text: list[str] = []
        self._folder_stack: list[str] = []
        self._pending_folder_name: str | None = None
        self._in_h3 = False

    def handle_starttag(self, tag, attrs) -> None:
        tag = tag.lower()
        if tag == "a":
            self._href = dict(attrs).get("href", "")
            self._text = []
        elif tag == "h3":
            self._in_h3 = True
            self._text = []
        elif tag == "dl":
            self._folder_stack.append(self._pending_folder_name or "")
            self._pending_folder_name = None

    def handle_data(self, data) -> None:
        if self._href or self._in_h3:
            self._text.append(data)

    def handle_endtag(self, tag) -> None:
        tag = tag.lower()
        if tag == "a" and self._href:
            # The outermost named folder is the browser's own root container
            # (Bookmarks bar, Other bookmarks, etc., not a folder the user made).
            parts = [part for part in self._folder_stack if part]
            folder = "/".join(parts[1:])
            self.entries.append((self._href, "".join(self._text).strip(), folder))
            self._href = ""
            self._text = []
        elif tag == "h3":
            self._in_h3 = False
            self._pending_folder_name = "".join(self._text).strip()
            self._text = []
        elif tag == "dl":
            if self._folder_stack:
                self._folder_stack.pop()


TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "utm_name",
    "fbclid", "gclid", "gclsrc", "dclid", "msclkid", "twclid", "yclid", "igshid",
    "mc_eid", "mc_cid", "ref_src", "vero_id", "mkt_tok", "_hsenc", "_hsmi", "oly_anon_id", "oly_enc_id",
}


def _strip_tracking_params(url: QUrl) -> QUrl | None:
    if not url.hasQuery():
        return None
    query = QUrlQuery(url)
    items = query.queryItems(QUrl.ComponentFormattingOption.FullyDecoded)
    kept = [(key, value) for key, value in items if key.lower() not in TRACKING_QUERY_PARAMS]
    if len(kept) == len(items):
        return None
    cleaned_query = QUrlQuery()
    cleaned_query.setQueryItems(kept)
    cleaned_url = QUrl(url)
    cleaned_url.setQuery(cleaned_query)
    return cleaned_url


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

        request_url = info.requestUrl()
        host = request_url.host().lower().rstrip(".")
        if any(host == domain or host.endswith("." + domain) for domain in self.blocked_domains):
            info.block(True)
            self.blocked.emit(first_party)
            return

        target_url = request_url
        if target_url.scheme() == "http" and target_url.host():
            target_url = QUrl(target_url)
            target_url.setScheme("https")

        if info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame:
            stripped = _strip_tracking_params(target_url)
            if stripped is not None:
                target_url = stripped

        if target_url != request_url:
            info.redirect(target_url)


class _LinuxPasswordVault:
    def __init__(self) -> None:
        self._connection = None
        self._collection = None

    def _get_collection(self, allow_unlock: bool = False):
        if secretstorage is None:
            raise RuntimeError("python-secretstorage is not installed.")
        if self._connection is None:
            self._connection = secretstorage.dbus_init()
        if not secretstorage.check_service_availability(self._connection):
            raise RuntimeError("No Secret Service provider is available in this session.")
        if self._collection is None:
            self._collection = secretstorage.get_default_collection(self._connection)
        if self._collection.is_locked():
            if not allow_unlock:
                raise RuntimeError("Password wallet is locked.")
            self._collection.unlock()
        return self._collection

    def save_credential(self, origin: str, username: str, password: str) -> None:
        collection = self._get_collection(allow_unlock=True)
        collection.create_item(
            f"ReyOS Browser: {origin} ({username})",
            {
                "application": "reyos-browser",
                "origin": origin,
                "username": username,
            },
            password.encode("utf-8"),
            replace=True,
        )

    def get_credentials(self, origin: str) -> list[dict]:
        try:
            collection = self._get_collection(allow_unlock=False)
        except RuntimeError:
            return []
        credentials = []
        for item in collection.search_items({"application": "reyos-browser", "origin": origin}):
            attributes = item.get_attributes()
            username = attributes.get("username", "").strip()
            if not username:
                continue
            credentials.append(
                {
                    "origin": origin,
                    "username": username,
                    "password": item.get_secret().decode("utf-8", errors="replace"),
                }
            )
        credentials.sort(key=lambda entry: entry["username"].lower())
        return credentials

    def delete_credential(self, origin: str, username: str) -> None:
        collection = self._get_collection(allow_unlock=True)
        for item in collection.search_items(
            {"application": "reyos-browser", "origin": origin, "username": username}
        ):
            item.delete()

    def list_all_origins(self) -> list[str]:
        try:
            collection = self._get_collection(allow_unlock=False)
        except RuntimeError:
            return []
        origins = {
            item.get_attributes().get("origin", "").strip()
            for item in collection.search_items({"application": "reyos-browser"})
        }
        return sorted(origin for origin in origins if origin)


class _WindowsPasswordVault:
    """Stores secrets in Windows Credential Manager via `keyring`.

    `keyring` only supports one password per (service, username) pair, so it
    can't answer "list every saved login for this origin" on its own. A small
    local index (origin -> usernames, no secrets) fills that gap; the actual
    passwords never leave Credential Manager.
    """

    def __init__(self) -> None:
        self._index_path = BROWSER_STATE_DIR / "password-index.json"

    @staticmethod
    def _service_name(origin: str) -> str:
        return f"reyos-browser:{origin}"

    def _require_keyring(self) -> None:
        if keyring is None:
            raise RuntimeError("The keyring package is not installed.")

    def _load_index(self) -> dict[str, list[str]]:
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_index(self, index: dict[str, list[str]]) -> None:
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._index_path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(index, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, self._index_path)

    def save_credential(self, origin: str, username: str, password: str) -> None:
        self._require_keyring()
        keyring.set_password(self._service_name(origin), username, password)
        index = self._load_index()
        usernames = index.setdefault(origin, [])
        if username not in usernames:
            usernames.append(username)
            self._save_index(index)

    def get_credentials(self, origin: str) -> list[dict]:
        if keyring is None:
            return []
        index = self._load_index()
        credentials = []
        for username in index.get(origin, []):
            password = keyring.get_password(self._service_name(origin), username)
            if password is None:
                continue
            credentials.append({"origin": origin, "username": username, "password": password})
        credentials.sort(key=lambda entry: entry["username"].lower())
        return credentials

    def delete_credential(self, origin: str, username: str) -> None:
        self._require_keyring()
        try:
            keyring.delete_password(self._service_name(origin), username)
        except keyring.errors.PasswordDeleteError:
            pass
        index = self._load_index()
        usernames = index.get(origin, [])
        if username in usernames:
            usernames.remove(username)
            if usernames:
                index[origin] = usernames
            else:
                index.pop(origin, None)
            self._save_index(index)

    def list_all_origins(self) -> list[str]:
        index = self._load_index()
        return sorted(origin for origin, usernames in index.items() if usernames)


PasswordVault = _WindowsPasswordVault if IS_WINDOWS else _LinuxPasswordVault


def normalize_origin(value: str) -> str:
    parsed = QUrl(value)
    scheme = parsed.scheme().lower()
    host = parsed.host().lower().rstrip(".")
    if scheme not in {"http", "https"} or not host:
        return ""
    port = parsed.port()
    if port != -1 and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


def _normalized_csv_header(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("_", "")


def _csv_row_value(row: dict, candidate_headers: set[str]) -> str:
    for key, value in row.items():
        if isinstance(key, str) and _normalized_csv_header(key) in candidate_headers:
            return value.strip() if isinstance(value, str) else ""
    return ""


def choose_open_file(start_dir: Path, title: str, filters: list[tuple[str, list[str]]]) -> str:
    dialog = QFileDialog()
    dialog.setWindowTitle(title)
    dialog.setDirectory(str(start_dir))
    dialog.setFileMode(QFileDialog.ExistingFile)
    dialog.setOption(QFileDialog.DontUseNativeDialog, True)
    dialog.setNameFilters([f"{label} ({' '.join(patterns)})" for label, patterns in filters])
    if not dialog.exec():
        return ""
    selected = dialog.selectedFiles()
    return selected[0].strip() if selected else ""


class PasswordBridge(QObject):
    savePromptRequested = Signal(str, str, str)

    def __init__(self, backend: "BrowserBackend") -> None:
        super().__init__()
        self._backend = backend
        self.setObjectName("passwordBridge")

    @Slot(str, str, str)
    def reportFormSubmit(self, origin: str, username: str, password: str) -> None:
        normalized_origin = normalize_origin(origin)
        cleaned_username = username.strip()
        if (
            not normalized_origin
            or not cleaned_username
            or not password
            or self._backend.isPasswordSaveBlocked(normalized_origin)
            or self._backend.hasSavedPassword(normalized_origin, cleaned_username, password)
        ):
            return
        self.savePromptRequested.emit(normalized_origin, cleaned_username, password)

    @Slot(str, result="QVariantList")
    def credentialsFor(self, origin: str):
        return self._backend.getPasswordsForOrigin(origin)


class BrowserBackend(QObject):
    shieldsChanged = Signal()
    lowMemoryChanged = Signal()
    blockedRequestCountChanged = Signal()
    currentSiteChanged = Signal()
    currentSiteShieldsChanged = Signal()
    searchEngineChanged = Signal()
    bookmarksChanged = Signal()
    passwordsChanged = Signal()
    bookmarkImportFinished = Signal(int, str)
    passwordImportFinished = Signal(int, str)
    shieldsUpdateFinished = Signal(bool, str)
    shieldsListInfoChanged = Signal()

    def __init__(
        self,
        interceptor: ShieldsInterceptor,
        password_vault: PasswordVault,
        password_script_source: str,
    ) -> None:
        super().__init__()
        self._interceptor = interceptor
        self._password_vault = password_vault
        self._password_script_source = password_script_source
        self._fingerprint_script_source = load_fingerprint_protection_script_source(secrets.token_hex(16))
        self._password_bridge = PasswordBridge(self)
        self._low_memory_mode = True
        self._blocked_request_count = 0
        self._current_site = ""
        self._search_engine = "DuckDuckGo"
        self._bookmarks_path = BROWSER_STATE_DIR / "bookmarks.json"
        self._password_blocklist_path = PASSWORD_BLOCKLIST_PATH
        self._bookmarks = self._load_bookmarks()
        self._password_blocklist = self._load_password_blocklist()
        interceptor.blocked.connect(self._record_blocked)
        self._shields_update_worker = None
        self._shields_updating = False
        self._shields_meta = load_shields_meta()

    @Property(QObject, constant=True)
    def passwordBridge(self) -> QObject:
        return self._password_bridge

    @Property(str, constant=True)
    def passwordScriptSource(self) -> str:
        return self._password_script_source

    @Property(str, constant=True)
    def fingerprintScriptSource(self) -> str:
        return self._fingerprint_script_source

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
            self._interceptor.blocked_domains = _parse_domain_lines(
                SHIELDS_CACHE_PATH.read_text(encoding="utf-8")
            )
            self._shields_meta = load_shields_meta()
        self.shieldsListInfoChanged.emit()
        self.shieldsUpdateFinished.emit(ok, message)

    def _load_bookmarks(self) -> list[dict]:
        try:
            data = json.loads(self._bookmarks_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [
                    entry
                    for entry in data
                    if isinstance(entry, dict) and isinstance(entry.get("url"), str)
                ]
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

    def _load_password_blocklist(self) -> list[str]:
        try:
            data = json.loads(self._password_blocklist_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                origins = {
                    origin
                    for origin in (
                        normalize_origin(entry) for entry in data if isinstance(entry, str)
                    )
                    if origin
                }
                return sorted(origins)
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _save_password_blocklist(self) -> None:
        self._password_blocklist_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp_path = self._password_blocklist_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(self._password_blocklist, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, self._password_blocklist_path)

    def isPasswordSaveBlocked(self, origin: str) -> bool:
        return normalize_origin(origin) in self._password_blocklist

    def hasSavedPassword(self, origin: str, username: str, password: str) -> bool:
        normalized_origin = normalize_origin(origin)
        cleaned_username = username.strip()
        if not normalized_origin or not cleaned_username or not password:
            return False
        try:
            for credential in self._password_vault.get_credentials(normalized_origin):
                if (
                    credential.get("username") == cleaned_username
                    and credential.get("password") == password
                ):
                    return True
        except Exception:
            return False
        return False

    @Property("QVariantList", notify=bookmarksChanged)
    def bookmarks(self):
        return self._bookmarks

    @Property(int, notify=bookmarksChanged)
    def bookmarksVersion(self) -> int:
        return len(self._bookmarks)

    @Property("QVariantList", notify=passwordsChanged)
    def passwordOrigins(self):
        try:
            return self._password_vault.list_all_origins()
        except Exception:
            return []

    @Slot(str, result=bool)
    def isBookmarked(self, url: str) -> bool:
        return any(item.get("url") == url for item in self._bookmarks)

    @Slot(str, str)
    def addBookmark(self, url: str, title: str) -> None:
        parsed = QUrl(url)
        if parsed.scheme() not in {"http", "https"} or not parsed.host() or self.isBookmarked(url):
            return
        self._bookmarks.append({"url": url, "title": (title or parsed.host()).strip()[:240], "folder": ""})
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
    def resetBookmarks(self) -> None:
        if not self._bookmarks:
            return
        self._bookmarks = []
        self._save_bookmarks()
        self.bookmarksChanged.emit()

    @Slot()
    def chooseBookmarkImport(self) -> None:
        try:
            path = choose_open_file(
                Path.home(),
                "Import Bookmarks",
                [("Bookmark HTML", ["*.html", "*.htm"]), ("All files", ["*"])],
            )
        except RuntimeError as error:
            self.bookmarkImportFinished.emit(0, f"Could not open bookmark picker: {error}")
            return
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
            by_url = {item.get("url"): item for item in self._bookmarks}
            added = 0
            updated = 0
            for url, title, folder in parser.entries:
                parsed = QUrl(url)
                if parsed.scheme() not in {"http", "https"} or not parsed.host():
                    continue
                folder = folder[:240]
                existing_item = by_url.get(url)
                if existing_item is None:
                    new_item = {
                        "url": url,
                        "title": (title or parsed.host()).strip()[:240],
                        "folder": folder,
                    }
                    self._bookmarks.append(new_item)
                    by_url[url] = new_item
                    added += 1
                elif folder and not existing_item.get("folder"):
                    existing_item["folder"] = folder
                    updated += 1
            if added or updated:
                self._save_bookmarks()
                self.bookmarksChanged.emit()
            parts = []
            if added:
                parts.append("imported {} bookmark{}".format(added, "s" if added != 1 else ""))
            if updated:
                parts.append("added folders to {} existing bookmark{}".format(updated, "s" if updated != 1 else ""))
            message = (", ".join(parts) + ".").capitalize() if parts else "No new bookmarks or folders found."
            self.bookmarkImportFinished.emit(added + updated, message)
        except (OSError, ValueError) as error:
            self.bookmarkImportFinished.emit(0, f"Could not import bookmarks: {error}")

    @Slot()
    def choosePasswordImport(self) -> None:
        try:
            path = choose_open_file(
                Path.home() / "Downloads",
                "Import Passwords",
                [("Password CSV", ["*.csv", "*.CSV"]), ("All files", ["*"])],
            )
        except RuntimeError as error:
            self.passwordImportFinished.emit(0, f"Could not open password picker: {error}")
            return
        if path:
            self.importPasswords(path)

    @Slot(str)
    def importPasswords(self, path: str) -> None:
        imported = 0
        skipped = 0
        try:
            password_file = Path(path)
            if password_file.stat().st_size > PASSWORD_IMPORT_MAX_BYTES:
                raise ValueError("The password file is too large.")
            with open(password_file, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise ValueError("The password file has no header row.")
                normalized_headers = {
                    _normalized_csv_header(name)
                    for name in reader.fieldnames
                    if isinstance(name, str)
                }
                if not normalized_headers & _PASSWORD_CSV_ORIGIN_HEADERS:
                    raise ValueError("The password file is missing a URL/origin column.")
                if not normalized_headers & _PASSWORD_CSV_USERNAME_HEADERS:
                    raise ValueError("The password file is missing a username column.")
                if not normalized_headers & _PASSWORD_CSV_PASSWORD_HEADERS:
                    raise ValueError("The password file is missing a password column.")
                for row in reader:
                    if not isinstance(row, dict):
                        skipped += 1
                        continue
                    raw_origin = _csv_row_value(row, _PASSWORD_CSV_ORIGIN_HEADERS)
                    normalized_origin = normalize_origin(raw_origin)
                    if (
                        not normalized_origin
                        and raw_origin
                        and "://" not in raw_origin
                        and "." in raw_origin
                        and " " not in raw_origin
                    ):
                        normalized_origin = normalize_origin("https://" + raw_origin)
                    username = _csv_row_value(row, _PASSWORD_CSV_USERNAME_HEADERS).strip()
                    password = _csv_row_value(row, _PASSWORD_CSV_PASSWORD_HEADERS)
                    if not normalized_origin or not username or not password:
                        skipped += 1
                        continue
                    if self.hasSavedPassword(normalized_origin, username, password):
                        skipped += 1
                        continue
                    self._password_vault.save_credential(normalized_origin, username, password)
                    imported += 1
        except (OSError, ValueError, csv.Error) as error:
            self.passwordImportFinished.emit(0, f"Could not import passwords: {error}")
            return
        except Exception as error:
            self.passwordImportFinished.emit(0, f"Could not import passwords: {error}")
            return

        self.passwordsChanged.emit()
        if imported == 1 and skipped == 0:
            message = "Imported 1 password."
        elif imported > 0 and skipped == 0:
            message = f"Imported {imported} passwords."
        elif imported > 0:
            message = f"Imported {imported} passwords, skipped {skipped} rows."
        elif skipped > 0:
            message = f"No passwords imported. Skipped {skipped} rows."
        else:
            message = "No passwords found in the file."
        self.passwordImportFinished.emit(imported, message)

    @Slot(str, str, str)
    def savePassword(self, origin: str, username: str, password: str) -> None:
        normalized_origin = normalize_origin(origin)
        cleaned_username = username.strip()
        if not normalized_origin or not cleaned_username or not password:
            return
        try:
            self._password_vault.save_credential(normalized_origin, cleaned_username, password)
        except Exception as error:
            self.notify("Passwords unavailable", str(error))
            return
        self.passwordsChanged.emit()

    @Slot(str, result="QVariantList")
    def getPasswordsForOrigin(self, origin: str):
        normalized_origin = normalize_origin(origin)
        if not normalized_origin:
            return []
        try:
            return self._password_vault.get_credentials(normalized_origin)
        except Exception:
            return []

    @Slot(str, str)
    def deletePassword(self, origin: str, username: str) -> None:
        normalized_origin = normalize_origin(origin)
        cleaned_username = username.strip()
        if not normalized_origin or not cleaned_username:
            return
        try:
            self._password_vault.delete_credential(normalized_origin, cleaned_username)
        except Exception as error:
            self.notify("Passwords unavailable", str(error))
            return
        self.passwordsChanged.emit()

    @Slot()
    def resetPasswords(self) -> None:
        try:
            origins = self._password_vault.list_all_origins()
            for origin in origins:
                for credential in self._password_vault.get_credentials(origin):
                    username = credential.get("username", "")
                    if username:
                        self._password_vault.delete_credential(origin, username)
        except Exception as error:
            self.notify("Passwords unavailable", str(error))
            return
        self.passwordsChanged.emit()

    @Slot(str)
    def blockPasswordSaveForOrigin(self, origin: str) -> None:
        normalized_origin = normalize_origin(origin)
        if not normalized_origin or normalized_origin in self._password_blocklist:
            return
        self._password_blocklist.append(normalized_origin)
        self._password_blocklist.sort()
        self._save_password_blocklist()

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

    @Slot()
    def persistShieldsStats(self) -> None:
        # Called once, on app quit -- rolls this session's in-memory count
        # into the durable lifetime total rather than replacing it, since
        # this method fires exactly once per session close, not per block.
        if self._blocked_request_count == 0:
            return
        try:
            existing = json.loads(SHIELDS_STATS_PATH.read_text(encoding="utf-8"))
            lifetime = existing.get("lifetimeBlocked", 0)
            if not isinstance(lifetime, int):
                lifetime = 0
        except (OSError, json.JSONDecodeError):
            lifetime = 0
        try:
            SHIELDS_STATE_DIR.mkdir(parents=True, exist_ok=True)
            SHIELDS_STATS_PATH.write_text(
                json.dumps({"lifetimeBlocked": lifetime + self._blocked_request_count}),
                encoding="utf-8",
            )
        except OSError:
            pass

    @Property(str, notify=searchEngineChanged)
    def searchEngine(self) -> str:
        return self._search_engine

    @Property(str, notify=searchEngineChanged)
    def searchBase(self) -> str:
        if self._search_engine == "DuckDuckGo":
            return "https://duckduckgo.com/?q="
        return "https://www.startpage.com/do/dsearch?query="

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
        """Send a desktop notification without retaining session data."""
        if IS_WINDOWS:
            # No native toast notifier is wired up yet on Windows (would need
            # win10toast/plyer or a WinRT toast call) — silently skip rather
            # than block on a missing dependency.
            return
        subprocess.Popen(
            ["notify-send", "-a", "ReyOS Browser", "-i", "reyos-browser", title, message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @Slot(result=bool)
    def openSystemPasswordManager(self) -> bool:
        if IS_WINDOWS:
            try:
                subprocess.Popen(["control.exe", "/name", "Microsoft.CredentialManager"])
                return True
            except OSError:
                self.notify(
                    "Password manager unavailable",
                    "Couldn't open Windows Credential Manager. Use Passwords in the browser menu instead.",
                )
                return False
        launch_commands = (
            ["kwalletmanager6"],
            ["kwalletmanager5"],
            ["kwalletmanager"],
            ["seahorse"],
            ["gtk-launch", "org.kde.kwalletmanager.desktop"],
            ["gtk-launch", "kwalletmanager5-kwalletd.desktop"],
        )
        for command in launch_commands:
            executable = shutil.which(command[0])
            if not executable:
                continue
            try:
                subprocess.Popen(
                    [executable, *command[1:]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                continue
            return True
        self.notify(
            "Password manager unavailable",
            "No supported system password manager is installed. Use Passwords in the browser menu, or install KWallet Manager.",
        )
        return False


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
            domains = _parse_domain_lines(
                SHIELDS_CACHE_PATH.read_text(encoding="utf-8", errors="replace")
            )
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


def load_password_script_source() -> str:
    qwebchannel_source = ""
    resource = QFile(":/qtwebchannel/qwebchannel.js")
    if resource.exists() and resource.open(QIODevice.ReadOnly | QIODevice.Text):
        qwebchannel_source = bytes(resource.readAll()).decode("utf-8", errors="replace")
        resource.close()
    if not qwebchannel_source:
        for path in QWEBCHANNEL_JS_PATHS:
            try:
                qwebchannel_source = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if qwebchannel_source:
                break
    autofill_source = PASSWORD_AUTOFILL_SCRIPT_PATH.read_text(encoding="utf-8")
    if qwebchannel_source:
        return qwebchannel_source + "\n\n" + autofill_source
    return (
        "window.console && console.warn('ReyOS Browser: qwebchannel.js could not be loaded; password autofill is disabled.');\n\n"
        + autofill_source
    )


def load_fingerprint_protection_script_source(session_key: str) -> str:
    source = FINGERPRINT_PROTECTION_SCRIPT_PATH.read_text(encoding="utf-8")
    return source.replace("%%SESSION_KEY%%", session_key)


class ShieldsUpdateWorker(QThread):
    finished_ok = Signal(bool, str, int)

    def run(self) -> None:
        domains: set[str] = set()
        fetched_sources = []
        for url in SHIELDS_LIST_URLS:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "ReyOS-Browser-Shields"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    raw = response.read().decode("utf-8", errors="replace")
            except (urllib.error.URLError, OSError, TimeoutError):
                # One source being unreachable shouldn't sink the whole
                # update -- merge whatever else succeeds, report only if
                # every source fails.
                continue
            parsed = _parse_domain_lines(raw)
            if len(parsed) < 500:
                # A genuine fetch of any of these lists is thousands of
                # domains -- a short/empty result means something upstream
                # broke (redirect to an HTML error page, truncated
                # response, wrong URL), not a real, safe-to-use list.
                continue
            domains |= parsed
            fetched_sources.append(url)

        if not fetched_sources:
            self.finished_ok.emit(
                False,
                "Could not reach any filter list server, or every response looked invalid -- kept the previous list.",
                0,
            )
            return

        try:
            SHIELDS_STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
            temp_path = SHIELDS_CACHE_PATH.with_suffix(".tmp")
            temp_path.write_text("\n".join(sorted(domains)) + "\n", encoding="utf-8")
            os.replace(temp_path, SHIELDS_CACHE_PATH)
            meta = {
                "source": ", ".join(fetched_sources),
                "lastUpdated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "domainCount": len(domains),
            }
            SHIELDS_META_PATH.write_text(json.dumps(meta), encoding="utf-8")
        except OSError as error:
            self.finished_ok.emit(False, f"Downloaded the list but could not save it: {error}", 0)
            return

        skipped = len(SHIELDS_LIST_URLS) - len(fetched_sources)
        note = (
            f" ({skipped} source{'s' if skipped != 1 else ''} unreachable, merged the rest)"
            if skipped
            else ""
        )
        self.finished_ok.emit(True, f"Filter list updated: {len(domains)} domains{note}.", len(domains))


def main():
    QtWebEngineQuick.initialize()
    app = QApplication(sys.argv)
    app.setApplicationName("ReyOS Browser")
    app.setDesktopFileName("reyos-browser")
    app.setOrganizationName("ReyOS")
    engine = QQmlApplicationEngine()
    interceptor = ShieldsInterceptor(load_blocked_domains())
    backend = BrowserBackend(interceptor, PasswordVault(), load_password_script_source())
    app.aboutToQuit.connect(backend.persistShieldsStats)
    engine.rootContext().setContextProperty("browserBackend", backend)
    engine.rootContext().setContextProperty("passwordBridge", backend.passwordBridge)
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
