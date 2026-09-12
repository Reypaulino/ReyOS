"""Writes real annotations into a PDF file -- highlights, free text notes,
and sticky-note comments -- so they're visible in any PDF viewer, not just
ReyOS Reader. Distinct from pdf.py (read-only QtPdf metadata/cover) and
pdf_tools.py (page-level merge/split, no annotation support in pypdf).

Uses PyMuPDF (imported as `pymupdf`, not the deprecated `fitz` alias) since
it can locate exact on-page rectangles for a text string via search_for(),
which is what makes turning a Qt-side text selection into a real highlight
annotation possible without needing pixel-perfect selection geometry from
QtQuick.Pdf's internals.

All three functions write to a temp file first and atomically replace the
original, since QtQuick.Pdf's QPdfDocument may still have the file open for
reading in the viewer -- the caller is responsible for telling that
QPdfDocument to reload afterward (there's no live in-process notification).
"""
import os
import tempfile
from pathlib import Path

import pymupdf


class PdfAnnotateError(Exception):
    pass


def _save_over(doc, path):
    """Saves and closes doc -- callers must not touch it again afterward
    (querying even doc.is_closed on an already-closed pymupdf Document
    raises), so this owns the one and only close() call for doc."""
    path = Path(path)
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=str(path.parent))
    os.close(fd)
    try:
        doc.save(tmp_path, garbage=3, deflate=True)
        doc.close()
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _open(path):
    try:
        return pymupdf.open(str(path))
    except Exception as e:
        raise PdfAnnotateError(f"Could not open {Path(path).name}: {e}")


def add_highlight(path, page_index, text):
    """Finds `text` on the given page and highlights every occurrence.
    Tries the exact selection first, then a whitespace-collapsed version,
    since a Qt text selection spanning a line wrap often joins lines with
    different whitespace than PyMuPDF's own text extraction does."""
    text = (text or "").strip()
    if not text:
        raise PdfAnnotateError("Nothing selected to highlight")
    doc = _open(path)
    saved = False
    try:
        if page_index < 0 or page_index >= doc.page_count:
            raise PdfAnnotateError("Page out of range")
        page = doc[page_index]
        quads = page.search_for(text, quads=True)
        if not quads:
            collapsed = " ".join(text.split())
            quads = page.search_for(collapsed, quads=True)
        if not quads:
            raise PdfAnnotateError("Could not locate the selected text on this page")
        annot = page.add_highlight_annot(quads)
        annot.update()
        _save_over(doc, path)
        saved = True
        return True
    finally:
        if not saved:
            doc.close()


def add_free_text(path, page_index, x, y, text, fontsize=12, width=220, height=80):
    """Places a free-floating text box at (x, y) in page points (top-left
    origin, matching a click position on a page image divided by that
    image's points-per-pixel scale)."""
    text = (text or "").strip()
    if not text:
        raise PdfAnnotateError("Text cannot be empty")
    doc = _open(path)
    saved = False
    try:
        if page_index < 0 or page_index >= doc.page_count:
            raise PdfAnnotateError("Page out of range")
        page = doc[page_index]
        rect = pymupdf.Rect(x, y, x + width, y + height)
        annot = page.add_freetext_annot(rect, text, fontsize=fontsize, text_color=(0, 0, 0), fill_color=(1, 1, 0.6))
        annot.update()
        _save_over(doc, path)
        saved = True
        return True
    finally:
        if not saved:
            doc.close()


def add_comment(path, page_index, x, y, text):
    """Places a sticky-note icon at (x, y) in page points; the note's text
    is the annotation's popup content, shown when the icon is opened."""
    text = (text or "").strip()
    if not text:
        raise PdfAnnotateError("Comment cannot be empty")
    doc = _open(path)
    saved = False
    try:
        if page_index < 0 or page_index >= doc.page_count:
            raise PdfAnnotateError("Page out of range")
        page = doc[page_index]
        annot = page.add_text_annot(pymupdf.Point(x, y), text)
        annot.update()
        _save_over(doc, path)
        saved = True
        return True
    finally:
        if not saved:
            doc.close()
