"""Library-folder scanning, off the GUI thread. Mirrors reyos-control-center-gui's
QThread-worker-emits-signal idiom (StatsWorker/PkgWorker) so a large library
never blocks the UI.
"""
import hashlib
import logging
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from formats import CBZ, CBR, EPUB, IMAGES, PDF, sniff_format
from formats.comic import ComicOpenError, extract_cover_bytes
from formats.epub import EpubBook, EpubOpenError
from formats.pdf import PdfOpenError, render_cover as render_pdf_cover
from library import Library

CACHE_DIR = Path.home() / ".cache" / "reyos-reader"
COVER_CACHE_DIR = CACHE_DIR / "covers"

log = logging.getLogger("reyos-reader.scanner")


def _cover_cache_path(source_path):
    digest = hashlib.sha256(str(source_path).encode()).hexdigest()[:32]
    return COVER_CACHE_DIR / f"{digest}.png"


def _extract_and_cache_cover(path, fmt):
    dest = _cover_cache_path(path)
    if dest.exists():
        return str(dest)
    COVER_CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        if fmt == EPUB:
            book = EpubBook(path)
            data = book.cover_bytes()
            if not data:
                return None
            image = QImage.fromData(data)
        elif fmt == PDF:
            image = render_pdf_cover(path)
        elif fmt in (CBZ, CBR, IMAGES):
            data = extract_cover_bytes(path, fmt)
            if not data:
                return None
            image = QImage.fromData(data)
        else:
            return None
        if image is None or image.isNull():
            return None
        if image.width() > 400:
            image = image.scaledToWidth(400)
        image.save(str(dest), "PNG")
        return str(dest)
    except (EpubOpenError, PdfOpenError, ComicOpenError):
        return None
    except Exception:
        log.warning("cover extraction failed for %s:\n%s", path, traceback.format_exc())
        return None


def extract_metadata(path, fmt):
    """Returns (title, author) or falls back to the filename per the spec's
    'never fail because metadata is missing' requirement."""
    title = path.stem
    author = None
    try:
        if fmt == EPUB:
            book = EpubBook(path)
            title = book.title() or title
            author = book.author()
        elif fmt == PDF:
            from formats.pdf import open_metadata

            pdf_title, _count, _doc = open_metadata(path)
            title = pdf_title or title
    except (EpubOpenError, PdfOpenError):
        pass
    except Exception:
        log.warning("metadata extraction failed for %s:\n%s", path, traceback.format_exc())
    return title, author


class ScanWorker(QThread):
    progress = Signal(str)
    itemFound = Signal()
    finishedScan = Signal(int, int)  # found, errors

    def __init__(self, db_path=None):
        super().__init__()
        self._db_path = db_path

    def run(self):
        lib = Library(self._db_path) if self._db_path else Library()
        found = 0
        errors = 0
        try:
            folders = lib.list_folders()
            seen_paths = set()
            for folder in folders:
                root = Path(folder["path"])
                if not root.is_dir():
                    continue
                self.progress.emit(f"Scanning {root}...")
                for entry in sorted(root.rglob("*")):
                    if not entry.is_file():
                        continue
                    fmt = sniff_format(entry)
                    if fmt is None:
                        continue
                    seen_paths.add(str(entry))
                    try:
                        title, author = extract_metadata(entry, fmt)
                        cover = _extract_and_cache_cover(entry, fmt)
                        lib.upsert_item(entry, folder["id"], title, author, fmt, cover)
                        found += 1
                        self.itemFound.emit()
                    except Exception:
                        errors += 1
                        log.warning("failed to index %s:\n%s", entry, traceback.format_exc())

            # Files that used to be indexed but disappeared: flag, don't delete.
            for item in lib.list_items():
                if item["path"] not in seen_paths and not Path(item["path"]).exists():
                    lib.mark_missing(item["id"], True)
                elif item["missing"] and Path(item["path"]).exists():
                    lib.mark_missing(item["id"], False)
        finally:
            lib.close()
        self.finishedScan.emit(found, errors)
