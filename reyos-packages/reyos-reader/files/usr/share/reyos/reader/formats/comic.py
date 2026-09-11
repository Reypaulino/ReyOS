"""CBZ/CBR/loose-image-folder page access.

Every backend exposes the same small interface (list_pages / read_page_bytes)
so the rest of the app (image provider, reader QML) never needs to know which
concrete archive type is open. Pages are decoded lazily, on request, one at a
time -- nothing here extracts a whole archive to disk.
"""
import re
import zipfile
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

_NUM_RE = re.compile(r"(\d+)")


def _natural_key(name):
    parts = _NUM_RE.split(name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


class ComicOpenError(Exception):
    pass


class CbzArchive:
    """CBZ (and generic image-only ZIP) backend, stdlib zipfile only."""

    def __init__(self, path):
        self.path = Path(path)
        try:
            self._zip = zipfile.ZipFile(self.path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            raise ComicOpenError(f"Could not open {self.path.name} as a CBZ archive") from exc
        names = [n for n in self._zip.namelist() if Path(n).suffix.lower() in IMAGE_SUFFIXES]
        self._pages = sorted(names, key=_natural_key)
        if not self._pages:
            raise ComicOpenError(f"{self.path.name} contains no readable images")

    def list_pages(self):
        return list(self._pages)

    def read_page_bytes(self, index):
        return self._zip.read(self._pages[index])

    def close(self):
        self._zip.close()


class CbrArchive:
    """CBR backend. Requires the optional `rarfile` module and a working
    `unrar` (or bsdtar) binary on PATH -- both are declared PKGBUILD
    dependencies, but this is kept import-guarded so a Reader build without
    them still runs for every other format instead of failing at import
    time.
    """

    def __init__(self, path):
        self.path = Path(path)
        try:
            import rarfile
        except ImportError as exc:
            raise ComicOpenError(
                "CBR support is unavailable -- the 'rarfile' module is not installed"
            ) from exc
        try:
            self._rar = rarfile.RarFile(str(self.path))
        except rarfile.Error as exc:
            raise ComicOpenError(f"Could not open {self.path.name} as a CBR archive") from exc
        names = [n for n in self._rar.namelist() if Path(n).suffix.lower() in IMAGE_SUFFIXES]
        self._pages = sorted(names, key=_natural_key)
        if not self._pages:
            raise ComicOpenError(f"{self.path.name} contains no readable images")

    def list_pages(self):
        return list(self._pages)

    def read_page_bytes(self, index):
        return self._rar.read(self._pages[index])

    def close(self):
        self._rar.close()


class ImageFolderArchive:
    """A plain directory of loose images, treated as a single "chapter"."""

    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_dir():
            raise ComicOpenError(f"{self.path} is not a directory")
        entries = [p for p in self.path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES]
        self._pages = sorted(entries, key=lambda p: _natural_key(p.name))
        if not self._pages:
            raise ComicOpenError(f"{self.path.name} contains no readable images")

    def list_pages(self):
        return [p.name for p in self._pages]

    def read_page_bytes(self, index):
        return self._pages[index].read_bytes()

    def close(self):
        pass


def open_comic(path, fmt):
    from . import CBZ, CBR, IMAGES

    if fmt == CBZ:
        return CbzArchive(path)
    if fmt == CBR:
        return CbrArchive(path)
    if fmt == IMAGES:
        return ImageFolderArchive(path)
    raise ComicOpenError(f"Unsupported comic format: {fmt}")


def extract_cover_bytes(path, fmt):
    """Return the first page's raw bytes, for cover-thumbnail generation."""
    archive = open_comic(path, fmt)
    try:
        if not archive.list_pages():
            return None
        return archive.read_page_bytes(0)
    finally:
        archive.close()
