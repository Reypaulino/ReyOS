"""Format detection for ReyOS Reader."""

EPUB = "epub"
PDF = "pdf"
CBZ = "cbz"
CBR = "cbr"
IMAGES = "images"

COMIC_FORMATS = (CBZ, CBR, IMAGES)

_EXTENSION_MAP = {
    ".epub": EPUB,
    ".pdf": PDF,
    ".cbz": CBZ,
    ".zip": CBZ,
    ".cbr": CBR,
    ".rar": CBR,
}


def sniff_format(path):
    """Return one of the format constants above, or None if unsupported."""
    suffix = path.suffix.lower()
    return _EXTENSION_MAP.get(suffix)


def is_supported(path):
    return sniff_format(path) is not None
