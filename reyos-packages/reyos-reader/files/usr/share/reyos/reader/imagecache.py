"""QQuickImageProvider backing comic (CBZ/CBR/image-folder) page display.

Memory strategy (see docs/reader.md "Memory-management strategy"): at most
MAX_CACHED_PAGES decoded QImages are kept at once, LRU-evicted. Combined
with Qt Quick's own delegate virtualization (only visible + a small
cacheBuffer of ListView delegates exist at all), this keeps memory bounded
regardless of how many pages the archive actually has. QQuickImageProvider
callbacks can arrive from a non-GUI thread when QML `Image` uses
asynchronous: true, so all shared state is guarded by a mutex.
"""
import logging
from collections import OrderedDict

from PySide6.QtCore import QMutex, QMutexLocker, QSize, Qt
from PySide6.QtGui import QIcon, QImage
from PySide6.QtQuick import QQuickImageProvider

from formats.comic import open_comic

MAX_CACHED_PAGES = 5

log = logging.getLogger("reyos-reader.imagecache")


class ComicImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._mutex = QMutex()
        self._archives = {}  # item_id (str) -> archive
        self._cache = OrderedDict()  # (item_id, page_index) -> QImage

    def open_item(self, item_id, path, fmt):
        with QMutexLocker(self._mutex):
            key = str(item_id)
            if key in self._archives:
                return len(self._archives[key].list_pages())
            archive = open_comic(path, fmt)
            self._archives[key] = archive
            return len(archive.list_pages())

    def close_item(self, item_id):
        with QMutexLocker(self._mutex):
            key = str(item_id)
            archive = self._archives.pop(key, None)
            if archive is not None:
                archive.close()
            for cache_key in [k for k in self._cache if k[0] == key]:
                del self._cache[cache_key]

    def requestImage(self, image_id, size, requested_size):
        # image_id format: "<item_id>/<page_index>"
        try:
            item_id, page_str = image_id.rsplit("/", 1)
            page_index = int(page_str)
        except ValueError:
            return QImage()

        cache_key = (item_id, page_index)
        with QMutexLocker(self._mutex):
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._cache.move_to_end(cache_key)
                if size is not None:
                    size.setWidth(cached.width())
                    size.setHeight(cached.height())
                return cached
            archive = self._archives.get(item_id)

        if archive is None:
            return QImage()

        try:
            data = archive.read_page_bytes(page_index)
            image = QImage.fromData(data)
        except Exception:
            log.warning("failed to decode page %s of %s", page_index, item_id, exc_info=True)
            return QImage()

        if image.isNull():
            return QImage()

        if requested_size is not None and requested_size.isValid():
            image = image.scaled(
                requested_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        with QMutexLocker(self._mutex):
            self._cache[cache_key] = image
            self._cache.move_to_end(cache_key)
            while len(self._cache) > MAX_CACHED_PAGES:
                self._cache.popitem(last=False)

        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image


class IconThemeProvider(QQuickImageProvider):
    """Backs "image://icontheme/<name>" for the QtQuick-Controls rewrite's
    Kirigami.Icon shim -- PySide6's QQmlApplicationEngine does not register
    an icon-theme provider on its own the way some C++ Qt apps get for free.
    """

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, name, size, requested_size):
        target_size = requested_size if requested_size.isValid() else QSize(48, 48)
        pixmap = QIcon.fromTheme(name).pixmap(target_size)
        if pixmap.isNull():
            image = QImage(target_size, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
        else:
            image = pixmap.toImage()
        if size is not None:
            size.setWidth(image.width())
            size.setHeight(image.height())
        return image
