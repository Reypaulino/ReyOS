"""EPUB parsing (ebooklib) and a locked-down `epub:` scheme handler for
rendering chapters through QWebEngineView without giving the book's own
markup any real network or filesystem access.

Registering the custom scheme must happen once, at process start, before a
QApplication/QWebEngineView exists -- see register_epub_scheme(), called
from main.py before QGuiApplication is constructed.
"""
import io
import mimetypes
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray
from PySide6.QtWebEngineCore import (
    QWebEngineUrlRequestInterceptor,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)

SCHEME = b"reyos-epub"


class EpubOpenError(Exception):
    pass


def register_epub_scheme():
    """Register the private `reyos-epub:` scheme. Local-only: no CORS grant
    to real network schemes, no special privilege beyond being loadable by
    QWebEngineView at all. Must run before QGuiApplication is created.
    """
    scheme = QWebEngineUrlScheme(SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Path)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.LocalAccessAllowed
        | QWebEngineUrlScheme.Flag.SecureScheme
    )
    QWebEngineUrlScheme.registerScheme(scheme)


class EpubBook:
    """Wraps an ebooklib EpubBook with the pieces Reader actually needs:
    metadata, a flat reading-order chapter list, a flattened TOC, and cover
    bytes. ebooklib reads the whole zip during epub.read_epub() -- there is
    no separate on-disk extraction step to avoid.
    """

    def __init__(self, path):
        from ebooklib import epub

        self.path = Path(path)
        try:
            self._book = epub.read_epub(str(self.path), options={"ignore_ncx": False})
        except Exception as exc:  # ebooklib raises plain Exception/ValueError on malformed files
            raise EpubOpenError(f"Could not open {self.path.name} as an EPUB") from exc

        self._items_by_name = {}
        for item in self._book.get_items():
            self._items_by_name[item.get_name()] = item

        self.chapters = self._build_spine()
        self.toc = self._build_toc()

    def _build_spine(self):
        chapters = []
        for idref, linear in self._book.spine:
            if linear == "no":
                continue
            item = self._book.get_item_with_id(idref)
            if item is not None:
                chapters.append(item.get_name())
        return chapters

    def _build_toc(self):
        entries = []

        def as_list(value):
            # Some real-world EPUBs (confirmed live with an Internet Archive
            # scan) give ebooklib a single-entry NCX that it parses down to
            # a bare epub.Link/Section instead of a one-item list -- treat
            # anything that isn't already a list/tuple as one node, not zero.
            if isinstance(value, (list, tuple)):
                return list(value)
            return [value]

        def walk(nodes):
            for node in as_list(nodes):
                if isinstance(node, tuple):
                    section, children = node
                    href = getattr(section, "href", "") or ""
                    title = getattr(section, "title", "") or href
                    entries.append({"title": title, "href": href.split("#")[0]})
                    walk(children)
                elif isinstance(node, list):
                    walk(node)
                else:
                    href = getattr(node, "href", "") or ""
                    title = getattr(node, "title", "") or href
                    entries.append({"title": title, "href": href.split("#")[0]})

        walk(self._book.toc)
        return entries

    def title(self):
        meta = self._book.get_metadata("DC", "title")
        return meta[0][0] if meta else self.path.stem

    def author(self):
        meta = self._book.get_metadata("DC", "creator")
        return meta[0][0] if meta else None

    def cover_bytes(self):
        import ebooklib

        cover_item = None
        for item in self._book.get_items_of_type(ebooklib.ITEM_COVER):
            cover_item = item
            break
        if cover_item is None:
            for item in self._book.get_items_of_type(ebooklib.ITEM_IMAGE):
                name = item.get_name().lower()
                if "cover" in name:
                    cover_item = item
                    break
        if cover_item is None:
            for item in self._book.get_items_of_type(ebooklib.ITEM_IMAGE):
                cover_item = item
                break
        return cover_item.get_content() if cover_item is not None else None

    def chapter_count(self):
        return len(self.chapters)

    def url_for_chapter(self, index):
        name = self.chapters[index]
        return f"{SCHEME.decode()}:///{name}"

    def resolve(self, item_path):
        """Look up an item by its zip-internal path for the scheme handler."""
        item_path = item_path.lstrip("/")
        if item_path in self._items_by_name:
            return self._items_by_name[item_path]
        # Some readers store spine items with a leading directory the
        # request URL normalizes away (or vice versa) -- fall back to a
        # basename match rather than failing the whole page over it.
        base = Path(item_path).name
        for name, item in self._items_by_name.items():
            if Path(name).name == base:
                return item
        return None


class EpubNavigationInterceptor(QWebEngineUrlRequestInterceptor):
    """Blocks every request that isn't our own `reyos-epub:` scheme -- the
    real security boundary for "no unrestricted access to the local
    machine." JavaScript is left enabled (needed for progress-restore
    scrolling, in-page find, and appearance-CSS injection via
    runJavaScript()), but content running in the reyos-epub origin has
    nowhere to go: no other origin, local file, or network host is ever
    reachable through this profile, regardless of what a book's markup or
    script tries to load.
    """

    def interceptRequest(self, info):
        if info.requestUrl().scheme() != SCHEME.decode():
            info.block(True)


class EpubSchemeHandler(QWebEngineUrlSchemeHandler):
    """Serves the currently-open EpubBook's own resources only. There is no
    reference to any other book, the filesystem, or the network here -- a
    request for a path this book doesn't contain simply fails.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._book = None

    def set_book(self, book):
        self._book = book

    def requestStarted(self, job):
        if self._book is None:
            job.fail(job.Error.RequestFailed)
            return
        item = self._book.resolve(job.requestUrl().path())
        if item is None:
            job.fail(job.Error.UrlNotFound)
            return
        content = item.get_content()
        mime = getattr(item, "media_type", None) or mimetypes.guess_type(item.get_name())[0] or "application/octet-stream"
        buf = QBuffer(job)
        buf.setData(QByteArray(content))
        buf.open(QBuffer.OpenModeFlag.ReadOnly)
        job.reply(mime.encode(), buf)
