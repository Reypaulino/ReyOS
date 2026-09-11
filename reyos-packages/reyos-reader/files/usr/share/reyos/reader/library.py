"""SQLite-backed library store. One connection, WAL mode, so a crash
mid-write can't corrupt the database (per docs/reader.md's persistence
model). All timestamps are ISO-8601 UTC strings.
"""
import datetime
import json
import sqlite3
from pathlib import Path

DATA_DIR = Path.home() / ".local" / "share" / "reyos-reader"
DB_PATH = DATA_DIR / "library.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS library_folders (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    library_folder_id INTEGER REFERENCES library_folders(id),
    title TEXT NOT NULL,
    author TEXT,
    format TEXT NOT NULL,
    cover_cache_path TEXT,
    added_at TEXT NOT NULL,
    last_opened_at TEXT,
    favorite INTEGER NOT NULL DEFAULT 0,
    reading_direction TEXT NOT NULL DEFAULT 'ltr',
    view_mode TEXT NOT NULL DEFAULT 'single',
    zoom REAL NOT NULL DEFAULT 1.0,
    progress_json TEXT,
    progress_percent REAL NOT NULL DEFAULT 0.0,
    missing INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    location_json TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS highlights (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    chapter INTEGER NOT NULL,
    range_json TEXT NOT NULL,
    color TEXT NOT NULL,
    snippet TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
"""


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Library:
    def __init__(self, db_path=DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self):
        self._conn.close()

    # -- library folders --------------------------------------------------

    def add_folder(self, path):
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO library_folders (path, added_at) VALUES (?, ?)",
                (str(path), _now()),
            )

    def remove_folder(self, folder_id):
        with self._conn:
            self._conn.execute("DELETE FROM library_folders WHERE id = ?", (folder_id,))

    def list_folders(self):
        return [dict(r) for r in self._conn.execute("SELECT * FROM library_folders ORDER BY path")]

    # -- items --------------------------------------------------------------

    def upsert_item(self, path, library_folder_id, title, author, fmt, cover_cache_path=None):
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO items (path, library_folder_id, title, author, format, cover_cache_path, added_at, missing)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(path) DO UPDATE SET
                    title=excluded.title,
                    author=excluded.author,
                    cover_cache_path=COALESCE(excluded.cover_cache_path, items.cover_cache_path),
                    missing=0
                """,
                (str(path), library_folder_id, title, author, fmt, cover_cache_path, _now()),
            )

    def mark_missing(self, item_id, missing=True):
        with self._conn:
            self._conn.execute("UPDATE items SET missing = ? WHERE id = ?", (1 if missing else 0, item_id))

    def get_item(self, item_id):
        row = self._conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def get_item_by_path(self, path):
        row = self._conn.execute("SELECT * FROM items WHERE path = ?", (str(path),)).fetchone()
        return dict(row) if row else None

    def list_items(self, fmt_filter=None):
        if fmt_filter and fmt_filter != "all":
            if fmt_filter == "manga":
                rows = self._conn.execute(
                    "SELECT * FROM items WHERE format IN ('cbz','cbr','images') AND reading_direction='rtl' ORDER BY title"
                )
            elif fmt_filter == "comics":
                rows = self._conn.execute(
                    "SELECT * FROM items WHERE format IN ('cbz','cbr','images') AND reading_direction='ltr' ORDER BY title"
                )
            elif fmt_filter == "books":
                rows = self._conn.execute("SELECT * FROM items WHERE format='epub' ORDER BY title")
            elif fmt_filter == "pdfs":
                rows = self._conn.execute("SELECT * FROM items WHERE format='pdf' ORDER BY title")
            else:
                rows = self._conn.execute("SELECT * FROM items ORDER BY title")
        else:
            rows = self._conn.execute("SELECT * FROM items ORDER BY title")
        return [dict(r) for r in rows]

    def list_continue_reading(self, limit=10):
        rows = self._conn.execute(
            "SELECT * FROM items WHERE last_opened_at IS NOT NULL AND missing = 0 "
            "AND progress_percent < 99.5 ORDER BY last_opened_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def list_recently_added(self, limit=20):
        rows = self._conn.execute("SELECT * FROM items ORDER BY added_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def list_favorites(self):
        rows = self._conn.execute("SELECT * FROM items WHERE favorite = 1 ORDER BY title")
        return [dict(r) for r in rows]

    def search(self, query):
        like = f"%{query.lower()}%"
        rows = self._conn.execute(
            "SELECT * FROM items WHERE lower(title) LIKE ? OR lower(author) LIKE ? ORDER BY title",
            (like, like),
        )
        return [dict(r) for r in rows]

    def set_favorite(self, item_id, favorite):
        with self._conn:
            self._conn.execute("UPDATE items SET favorite = ? WHERE id = ?", (1 if favorite else 0, item_id))

    def set_reading_direction(self, item_id, direction):
        with self._conn:
            self._conn.execute("UPDATE items SET reading_direction = ? WHERE id = ?", (direction, item_id))

    def set_view_mode(self, item_id, view_mode):
        with self._conn:
            self._conn.execute("UPDATE items SET view_mode = ? WHERE id = ?", (view_mode, item_id))

    def set_zoom(self, item_id, zoom):
        with self._conn:
            self._conn.execute("UPDATE items SET zoom = ? WHERE id = ?", (zoom, item_id))

    def save_progress(self, item_id, location, percent):
        with self._conn:
            self._conn.execute(
                "UPDATE items SET progress_json = ?, progress_percent = ?, last_opened_at = ? WHERE id = ?",
                (json.dumps(location), percent, _now(), item_id),
            )

    def remove_item(self, item_id):
        """Remove from library only -- never touches the source file."""
        with self._conn:
            self._conn.execute("DELETE FROM items WHERE id = ?", (item_id,))

    # -- bookmarks ------------------------------------------------------

    def add_bookmark(self, item_id, location, label=None):
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO bookmarks (item_id, location_json, label, created_at) VALUES (?, ?, ?, ?)",
                (item_id, json.dumps(location), label, _now()),
            )
            return cur.lastrowid

    def list_bookmarks(self, item_id):
        rows = self._conn.execute(
            "SELECT * FROM bookmarks WHERE item_id = ? ORDER BY created_at", (item_id,)
        )
        result = []
        for r in rows:
            d = dict(r)
            d["location"] = json.loads(d["location_json"])
            result.append(d)
        return result

    def remove_bookmark(self, bookmark_id):
        with self._conn:
            self._conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))

    # -- highlights ---------------------------------------------------------

    def add_highlight(self, item_id, chapter, range_dict, color, snippet, note=None):
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO highlights (item_id, chapter, range_json, color, snippet, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (item_id, chapter, json.dumps(range_dict), color, snippet, note, _now()),
            )
            return cur.lastrowid

    def list_highlights(self, item_id):
        rows = self._conn.execute(
            "SELECT * FROM highlights WHERE item_id = ? ORDER BY chapter, created_at", (item_id,)
        )
        result = []
        for r in rows:
            d = dict(r)
            d["range"] = json.loads(d["range_json"])
            result.append(d)
        return result

    def list_highlights_for_chapter(self, item_id, chapter):
        rows = self._conn.execute(
            "SELECT * FROM highlights WHERE item_id = ? AND chapter = ? ORDER BY created_at",
            (item_id, chapter),
        )
        result = []
        for r in rows:
            d = dict(r)
            d["range"] = json.loads(d["range_json"])
            result.append(d)
        return result

    def remove_highlight(self, highlight_id):
        with self._conn:
            self._conn.execute("DELETE FROM highlights WHERE id = ?", (highlight_id,))

    def update_highlight_note(self, highlight_id, note):
        with self._conn:
            self._conn.execute("UPDATE highlights SET note = ? WHERE id = ?", (note, highlight_id))
