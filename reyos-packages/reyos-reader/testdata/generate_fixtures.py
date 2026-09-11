#!/usr/bin/env python3
"""Generates synthetic, public-domain-safe test fixtures for ReyOS Reader --
never real copyrighted books/manga (see docs/reader.md Testing plan). Run
with QT_QPA_PLATFORM=offscreen on the Dev VM (needs pyside6 + ebooklib,
both real ReyOS Reader dependencies already installed there).
"""
import os
import random
import sys
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, QSizeF
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPdfWriter
from PySide6.QtWidgets import QApplication

OUT = Path(__file__).resolve().parent


def make_page_image(width, height, text, bg):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(bg))
    painter = QPainter(image)
    painter.setPen(QColor("#FFFFFF") if QColor(bg).lightness() < 128 else QColor("#000000"))
    painter.setFont(QFont("sans-serif", height // 12))
    painter.drawText(image.rect(), 0x0084, text)  # Qt.AlignCenter
    painter.end()
    return image


def build_cbz(path, page_count, width, height):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(page_count):
            hue = (i * 37) % 360
            color = QColor.fromHsv(hue, 120, 60)
            img = make_page_image(width, height, f"Page {i + 1}", color.name())
            tmp = OUT / f"_tmp_page_{i}.jpg"
            img.save(str(tmp), "JPEG", quality=85)
            zf.write(tmp, f"page_{i:03d}.jpg")
            tmp.unlink()


def build_epub_simple(path):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("reyos-reader-fixture-simple")
    book.set_title("ReyOS Reader Test Book")
    book.set_language("en")
    book.add_author("ReyOS Test Fixtures")

    chapter = epub.EpubHtml(title="Chapter 1", file_name="chap1.xhtml", lang="en")
    chapter.content = (
        "<h1>Chapter 1</h1>"
        "<p>" + " ".join(["This is a generated, public-domain test paragraph."] * 40) + "</p>"
    )
    book.add_item(chapter)
    book.toc = (epub.Link("chap1.xhtml", "Chapter 1", "chap1"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(str(path), book)


def build_epub_multichapter(path, chapters=5):
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("reyos-reader-fixture-multi")
    book.set_title("ReyOS Reader Test Book — Multi Chapter")
    book.set_language("en")
    book.add_author("ReyOS Test Fixtures")

    items = []
    toc = []
    for i in range(1, chapters + 1):
        c = epub.EpubHtml(title=f"Chapter {i}", file_name=f"chap{i}.xhtml", lang="en")
        c.content = (
            f"<h1>Chapter {i}</h1>"
            "<p>" + " ".join([f"Generated paragraph text for chapter {i}."] * 60) + "</p>"
        )
        book.add_item(c)
        items.append(c)
        toc.append(epub.Link(f"chap{i}.xhtml", f"Chapter {i}", f"chap{i}"))

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + items
    epub.write_epub(str(path), book)


def build_pdf(path, pages=6):
    writer = QPdfWriter(str(path))
    painter = QPainter(writer)
    for i in range(pages):
        if i > 0:
            writer.newPage()
        painter.setFont(QFont("sans-serif", 24))
        painter.drawText(QRectF(0, 0, painter.viewport().width(), painter.viewport().height()),
                          0x0084, f"ReyOS Reader Test PDF\nPage {i + 1} of {pages}")
    painter.end()


def build_corrupt_cbz(path):
    path.write_bytes(b"This is not a real zip file, on purpose.\x00\x01\x02")


def main():
    app = QGuiApplication(sys.argv)

    build_epub_simple(OUT / "simple.epub")
    build_epub_multichapter(OUT / "multichapter.epub")
    build_cbz(OUT / "small.cbz", page_count=20, width=800, height=1200)
    build_cbz(OUT / "large.cbz", page_count=150, width=2000, height=3000)
    build_pdf(OUT / "sample.pdf", pages=6)
    build_corrupt_cbz(OUT / "corrupt.cbz")

    print("Fixtures written to", OUT)


if __name__ == "__main__":
    main()
