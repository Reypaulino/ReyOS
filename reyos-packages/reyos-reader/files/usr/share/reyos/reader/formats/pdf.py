"""PDF metadata/cover helpers. Page rendering itself is done in QML by
QtQuick.Pdf's PdfDocument/PdfMultiPageView -- this module only extracts what
the library scanner needs (title, page count, a first-page thumbnail) and
never rasterizes the whole document.
"""
from pathlib import Path

from PySide6.QtCore import QSizeF
from PySide6.QtPdf import QPdfDocument


class PdfOpenError(Exception):
    pass


class PdfEncryptedError(PdfOpenError):
    pass


def open_metadata(path):
    """Returns (title, page_count) or raises PdfOpenError/PdfEncryptedError."""
    path = Path(path)
    doc = QPdfDocument()
    status = doc.load(str(path))
    if status == QPdfDocument.Error.IncorrectPassword:
        raise PdfEncryptedError(f"{path.name} is password-protected")
    if status != QPdfDocument.Error.None_:
        raise PdfOpenError(f"Could not open {path.name} as a PDF")
    title = doc.metaData(QPdfDocument.MetaDataField.Title) or path.stem
    page_count = doc.pageCount()
    return str(title), page_count, doc


def render_cover(path, max_width=400):
    """Render page 0 at a bounded width for the library cover cache."""
    try:
        title, page_count, doc = open_metadata(path)
    except PdfOpenError:
        return None
    if page_count == 0:
        return None
    page_size = doc.pagePointSize(0)
    if page_size.width() <= 0:
        return None
    scale = max_width / page_size.width()
    target = QSizeF(page_size.width() * scale, page_size.height() * scale).toSize()
    image = doc.render(0, target)
    return image
