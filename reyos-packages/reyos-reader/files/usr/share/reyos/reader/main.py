#!/usr/bin/env python3
import json
import logging
import re
import sys
import traceback
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from PySide6.QtCore import Property, QObject, QThread, QUrl, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWebEngineQuick import QtWebEngineQuick
from PySide6.QtWidgets import QApplication

from formats import CBZ, CBR, EPUB, IMAGES, PDF, sniff_format
from formats.comic import ComicOpenError
from formats.epub import (
    EpubBook,
    EpubNavigationInterceptor,
    EpubOpenError,
    EpubSchemeHandler,
    register_epub_scheme,
)
from formats.pdf import PdfEncryptedError, PdfOpenError, open_metadata as open_pdf_metadata
from formats import pdf_tools
from imagecache import ComicImageProvider, IconThemeProvider
from library import Library
from scanner import ScanWorker, extract_metadata

LOG_DIR = Path.home() / ".cache" / "reyos-reader"
LOG_FILE = LOG_DIR / "reyos-reader.log"

SUPPORTED_OPEN_FILTER = "Books and comics (*.epub *.pdf *.cbz *.cbr *.zip *.rar)"
HIGHLIGHTER_SCRIPT_PATH = APP_DIR / "highlighter.js"


def load_highlighter_script_source():
    try:
        return HIGHLIGHTER_SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def _setup_logging():
    LOG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_FILE),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


log = logging.getLogger("reyos-reader")


class PdfToolWorker(QThread):
    """Runs a merge/split off the UI thread -- large PDFs can take a
    noticeable moment. Mirrors the ActionWorker convention used in
    reyos-connect's main.py (separate package, not shared code)."""
    finished_ok = Signal(bool, str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            result = self.fn()
            self.finished_ok.emit(True, result)
        except pdf_tools.PdfToolError as e:
            self.finished_ok.emit(False, str(e))
        except Exception as e:
            log.exception("PDF tool operation failed")
            self.finished_ok.emit(False, f"Unexpected error: {e}")


class Backend(QObject):
    libraryChanged = Signal()
    scanProgress = Signal(str)
    scanFinished = Signal(int, int)

    epubReady = Signal(int, str)     # item_id, json meta
    pdfReady = Signal(int, str)
    pdfPreviewReady = Signal(str)  # metaJson -- not added to the library
    comicReady = Signal(int, str)
    openFailed = Signal(str, str)    # friendly message, technical detail
    pdfToolFinished = Signal(bool, str)  # ok, output path or error message
    highlightsChanged = Signal()

    def __init__(self, image_provider, scheme_handler):
        super().__init__()
        self._lib = Library()
        self._image_provider = image_provider
        self._scheme_handler = scheme_handler
        self._highlighter_script_source = load_highlighter_script_source()
        self._current_epub = None
        self._current_epub_item_id = None
        self._scan_worker = None
        self._pdf_workers = []

    @Property(str, constant=True)
    def highlighterScriptSource(self):
        return self._highlighter_script_source

    # -- helpers ----------------------------------------------------------

    def _items_json(self, items):
        return json.dumps(items)

    def _fail(self, friendly, exc=None):
        technical = traceback.format_exc() if exc is not None else ""
        if exc is not None:
            log.warning("%s: %s", friendly, exc)
        self.openFailed.emit(friendly, technical)

    # -- library browsing ---------------------------------------------------

    @Slot(str, result=str)
    def getLibrary(self, fmt_filter):
        return self._items_json(self._lib.list_items(fmt_filter))

    @Slot(result=str)
    def getContinueReading(self):
        return self._items_json(self._lib.list_continue_reading())

    @Slot(result=str)
    def getFavorites(self):
        return self._items_json(self._lib.list_favorites())

    @Slot(result=str)
    def getRecentlyAdded(self):
        return self._items_json(self._lib.list_recently_added())

    @Slot(str, result=str)
    def search(self, query):
        return self._items_json(self._lib.search(query))

    @Slot(result=str)
    def listFolders(self):
        return self._items_json(self._lib.list_folders())

    @Slot(int, bool)
    def setFavorite(self, item_id, favorite):
        self._lib.set_favorite(item_id, favorite)
        self.libraryChanged.emit()

    @Slot(int)
    def removeFromLibrary(self, item_id):
        self._lib.remove_item(item_id)
        self.libraryChanged.emit()

    @Slot(int, str)
    def setReadingDirection(self, item_id, direction):
        self._lib.set_reading_direction(item_id, direction)

    @Slot(int, str)
    def setViewMode(self, item_id, view_mode):
        self._lib.set_view_mode(item_id, view_mode)

    @Slot(int, float)
    def setZoom(self, item_id, zoom):
        self._lib.set_zoom(item_id, zoom)

    @Slot(int, str, float)
    def saveProgress(self, item_id, location_json, percent):
        try:
            location = json.loads(location_json)
        except ValueError:
            location = {}
        self._lib.save_progress(item_id, location, percent)

    @Slot(int, str, str)
    def addBookmark(self, item_id, location_json, label):
        try:
            location = json.loads(location_json)
        except ValueError:
            location = {}
        self._lib.add_bookmark(item_id, location, label or None)

    @Slot(int, result=str)
    def listBookmarks(self, item_id):
        return self._items_json(self._lib.list_bookmarks(item_id))

    @Slot(int)
    def removeBookmark(self, bookmark_id):
        self._lib.remove_bookmark(bookmark_id)

    # -- highlights -----------------------------------------------------------

    @Slot(int, int, str, str, str, str, result=int)
    def addHighlight(self, item_id, chapter, range_json, color, snippet, note):
        try:
            range_dict = json.loads(range_json)
        except ValueError:
            return -1
        highlight_id = self._lib.add_highlight(item_id, chapter, range_dict, color, snippet, note or None)
        self.highlightsChanged.emit()
        return highlight_id

    @Slot(int, result=str)
    def listHighlights(self, item_id):
        return self._items_json(self._lib.list_highlights(item_id))

    @Slot(int, int, result=str)
    def listHighlightsForChapter(self, item_id, chapter):
        return self._items_json(self._lib.list_highlights_for_chapter(item_id, chapter))

    @Slot(int)
    def removeHighlight(self, highlight_id):
        self._lib.remove_highlight(highlight_id)
        self.highlightsChanged.emit()

    @Slot(int, str)
    def updateHighlightNote(self, highlight_id, note):
        self._lib.update_highlight_note(highlight_id, note or None)
        self.highlightsChanged.emit()

    @Slot(int, result=str)
    def exportHighlights(self, item_id):
        """Kindle "My Clippings.txt"-style export: writes every highlight
        for this book, in chapter order, to a plain-text file the user
        picks. Returns the chosen path, or "" if cancelled/failed."""
        from PySide6.QtWidgets import QFileDialog

        item = self._lib.get_item(item_id)
        if item is None:
            return ""
        highlights = self._lib.list_highlights(item_id)
        if not highlights:
            return ""

        default_name = re.sub(r"[^\w\- ]", "", item["title"]).strip() or "highlights"
        path, _filter = QFileDialog.getSaveFileName(
            None, "Export Highlights", str(Path.home() / f"{default_name} - Highlights.txt"),
            "Text files (*.txt)",
        )
        if not path:
            return ""
        if not path.lower().endswith(".txt"):
            path += ".txt"

        lines = [item["title"], "=" * len(item["title"]), ""]
        for h in highlights:
            lines.append(f"Chapter {h['chapter'] + 1}")
            lines.append(f"“{h['snippet']}”")
            if h.get("note"):
                lines.append(f"Note: {h['note']}")
            lines.append("")
        try:
            Path(path).write_text("\n".join(lines), encoding="utf-8")
        except OSError as error:
            self.openFailed.emit(f"Could not save highlights: {error}", str(path))
            return ""
        return path

    # -- adding content -----------------------------------------------------

    @Slot()
    def addFolder(self):
        from PySide6.QtWidgets import QFileDialog

        path = QFileDialog.getExistingDirectory(None, "Add Library Folder", str(Path.home()))
        if path:
            self._lib.add_folder(path)
            self.refreshLibrary()

    @Slot(int)
    def removeFolder(self, folder_id):
        self._lib.remove_folder(folder_id)
        self.libraryChanged.emit()

    @Slot()
    def refreshLibrary(self):
        if self._scan_worker is not None and self._scan_worker.isRunning():
            return
        self._scan_worker = ScanWorker()
        self._scan_worker.progress.connect(self.scanProgress.emit)
        self._scan_worker.itemFound.connect(self.libraryChanged.emit)

        def on_finished(found, errors):
            self.libraryChanged.emit()
            self.scanFinished.emit(found, errors)

        self._scan_worker.finishedScan.connect(on_finished)
        self._scan_worker.start()

    @Slot()
    def openFileDialog(self):
        from PySide6.QtWidgets import QFileDialog

        path, _filter = QFileDialog.getOpenFileName(None, "Open File", str(Path.home()), SUPPORTED_OPEN_FILTER)
        if path:
            self.openPath(path)

    @Slot(str)
    def openPath(self, path):
        p = Path(path)
        fmt = sniff_format(p)
        if fmt is None:
            self.openFailed.emit("ReyOS Reader does not support this file type.", str(p))
            return
        existing = self._lib.get_item_by_path(p)
        if existing is None:
            title, author = extract_metadata(p, fmt)
            self._lib.upsert_item(p, None, title, author, fmt)
            existing = self._lib.get_item_by_path(p)
        self.openItem(existing["id"])

    # -- opening for reading --------------------------------------------------

    @Slot(int)
    def openItem(self, item_id):
        item = self._lib.get_item(item_id)
        if item is None:
            self.openFailed.emit("This item is no longer in your library.", f"item_id={item_id}")
            return
        path = Path(item["path"])
        if not path.exists():
            self._lib.mark_missing(item_id, True)
            self.libraryChanged.emit()
            self.openFailed.emit(f'"{item["title"]}" could not be found. It may have been moved or deleted.', str(path))
            return

        fmt = item["format"]
        try:
            if fmt == EPUB:
                self._open_epub(item)
            elif fmt == PDF:
                self._open_pdf(item)
            elif fmt in (CBZ, CBR, IMAGES):
                self._open_comic(item)
            else:
                self.openFailed.emit("ReyOS Reader could not open this file.", f"unknown format {fmt}")
                return
        except EpubOpenError as exc:
            self._fail("ReyOS Reader could not open this EPUB. The file may be corrupt.", exc)
        except (PdfEncryptedError,) as exc:
            self._fail("This PDF is password-protected. ReyOS Reader cannot open encrypted PDFs yet.", exc)
        except PdfOpenError as exc:
            self._fail("ReyOS Reader could not open this PDF. The file may be corrupt.", exc)
        except ComicOpenError as exc:
            self._fail("ReyOS Reader could not open this archive. It may be corrupt or in an unsupported format.", exc)
        except Exception as exc:  # last resort -- never let a bad file crash the library
            self._fail("ReyOS Reader could not open this file.", exc)

    def _open_epub(self, item):
        book = EpubBook(item["path"])
        self._current_epub = book
        self._current_epub_item_id = item["id"]
        self._scheme_handler.set_book(book)
        progress = json.loads(item["progress_json"]) if item["progress_json"] else {}
        meta = {
            "id": item["id"],
            "title": book.title(),
            "author": book.author(),
            "chapterCount": book.chapter_count(),
            "toc": book.toc,
            "chapterUrls": [book.url_for_chapter(i) for i in range(book.chapter_count())],
            "startChapter": progress.get("chapter", 0),
            "startScrollFrac": progress.get("scroll_frac", 0.0),
        }
        self._lib.save_progress(item["id"], progress, item["progress_percent"])
        self.epubReady.emit(item["id"], json.dumps(meta))

    def _open_pdf(self, item):
        title, page_count, _doc = open_pdf_metadata(item["path"])
        progress = json.loads(item["progress_json"]) if item["progress_json"] else {}
        meta = {
            "id": item["id"],
            "title": title,
            "path": QUrl.fromLocalFile(str(item["path"])).toString(),
            "pageCount": page_count,
            "startPage": progress.get("page", 0),
            "zoom": item["zoom"],
        }
        self._lib.save_progress(item["id"], progress, item["progress_percent"])
        self.pdfReady.emit(item["id"], json.dumps(meta))

    @Slot(str)
    def previewPdf(self, path):
        """Opens a PDF for viewing without adding it to the library -- used
        by PDF Tools' Split card so a user can check page numbers before
        typing a range, without polluting their library with a file they
        may not want to keep (unlike openPath(), which always upserts)."""
        p = Path(path)
        try:
            title, page_count, _doc = open_pdf_metadata(p)
        except (PdfOpenError, PdfEncryptedError) as error:
            self.openFailed.emit(f"Could not open PDF: {error}", str(p))
            return
        meta = {
            "id": -1,
            "title": title,
            "path": QUrl.fromLocalFile(str(p)).toString(),
            "pageCount": page_count,
            "startPage": 0,
            "zoom": 0,
        }
        self.pdfPreviewReady.emit(json.dumps(meta))

    def _open_comic(self, item):
        page_count = self._image_provider.open_item(item["id"], item["path"], item["format"])
        progress = json.loads(item["progress_json"]) if item["progress_json"] else {}
        meta = {
            "id": item["id"],
            "title": item["title"],
            "pageCount": page_count,
            "startPage": min(progress.get("page", 0), max(page_count - 1, 0)),
            "direction": item["reading_direction"],
            "viewMode": item["view_mode"],
            "zoom": item["zoom"],
        }
        self._lib.save_progress(item["id"], progress, item["progress_percent"])
        self.comicReady.emit(item["id"], json.dumps(meta))

    @Slot(int)
    def closeComic(self, item_id):
        self._image_provider.close_item(item_id)

    @Slot()
    def closeEpub(self):
        self._scheme_handler.set_book(None)
        self._current_epub = None
        self._current_epub_item_id = None

    # -- PDF Tools (merge/split) ---------------------------------------------

    def _run_pdf_tool(self, fn):
        worker = PdfToolWorker(fn)
        worker.finished_ok.connect(self.pdfToolFinished.emit)
        worker.finished_ok.connect(lambda *_: self._pdf_workers.remove(worker) if worker in self._pdf_workers else None)
        self._pdf_workers.append(worker)
        worker.start()

    @Slot(result="QVariantList")
    def pickPdfsToMerge(self):
        from PySide6.QtWidgets import QFileDialog

        paths, _filter = QFileDialog.getOpenFileNames(
            None, "Select PDFs to Merge", str(Path.home()), "PDF files (*.pdf)")
        return paths

    @Slot(result=str)
    def pickPdfToSplit(self):
        from PySide6.QtWidgets import QFileDialog

        path, _filter = QFileDialog.getOpenFileName(
            None, "Select PDF to Split", str(Path.home()), "PDF files (*.pdf)")
        return path

    @Slot(str, result=str)
    def pickPdfSaveAs(self, default_name):
        from PySide6.QtWidgets import QFileDialog

        path, _filter = QFileDialog.getSaveFileName(
            None, "Save PDF As", str(Path.home() / default_name), "PDF files (*.pdf)")
        if path and not path.lower().endswith(".pdf"):
            path += ".pdf"
        return path

    @Slot(str, result=int)
    def pdfPageCount(self, path):
        try:
            return pdf_tools.page_count(path)
        except pdf_tools.PdfToolError:
            return 0

    @Slot("QVariantList", str)
    def mergePdfs(self, paths, output_path):
        input_paths = list(paths)
        self._run_pdf_tool(lambda: pdf_tools.merge_pdfs(input_paths, output_path))

    @Slot(str, str, str)
    def splitPdf(self, input_path, output_path, ranges_str):
        self._run_pdf_tool(lambda: pdf_tools.split_pdf(input_path, output_path, ranges_str))


def main():
    _setup_logging()
    register_epub_scheme()

    QtWebEngineQuick.initialize()
    app = QApplication(sys.argv)
    app.setApplicationName("ReyOS Reader")
    app.setDesktopFileName("reyos-reader")
    app.setOrganizationName("ReyOS")

    engine = QQmlApplicationEngine()

    image_provider = ComicImageProvider()
    engine.addImageProvider("reyospage", image_provider)
    engine.addImageProvider("icontheme", IconThemeProvider())

    scheme_handler = EpubSchemeHandler()
    nav_interceptor = EpubNavigationInterceptor()
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings

    profile = QWebEngineProfile.defaultProfile()
    profile.installUrlSchemeHandler(b"reyos-epub", scheme_handler)
    # nav_interceptor blocks every request outside our own reyos-epub scheme
    # (no network, no other local file) -- that's the real containment
    # boundary, not JavascriptEnabled, which stays on so runJavaScript()
    # (progress-restore scroll, in-page find, appearance CSS) keeps working.
    profile.setUrlRequestInterceptor(nav_interceptor)
    settings = profile.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
    settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)

    backend = Backend(image_provider, scheme_handler)
    # The library's sqlite connection is deliberately left open for the
    # process's whole lifetime rather than closed on aboutToQuit: QML page
    # teardown (BookReaderPage/ComicReaderPage's Component.onDestruction,
    # which calls saveProgress()) happens after aboutToQuit fires, so
    # closing the connection there raced it and crashed with "Cannot
    # operate on a closed database" (confirmed live on the Dev VM). Process
    # exit releases the handle safely; every write already commits via its
    # own `with self._conn:` transaction, so there's nothing left to flush.
    engine.rootContext().setContextProperty("backend", backend)

    engine.load(QUrl.fromLocalFile(str(APP_DIR / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1

    window = engine.rootObjects()[0]
    window.setIcon(QIcon.fromTheme("reyos-reader"))

    def try_activate(remaining=6):
        window.raise_()
        window.requestActivate()
        if remaining > 0:
            QTimer.singleShot(300, lambda: try_activate(remaining - 1))

    QTimer.singleShot(200, try_activate)

    # `Exec=reyos-reader %U` in the .desktop file means a file manager or
    # "Open With" can launch a brand-new process with the file path as an
    # argument -- open it once the window/backend are ready, same pattern
    # as try_activate above.
    file_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if file_args:
        QTimer.singleShot(250, lambda: backend.openPath(file_args[0]))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
