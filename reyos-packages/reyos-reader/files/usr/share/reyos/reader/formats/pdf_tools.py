"""PDF merge/split -- real page-level manipulation, distinct from pdf.py's
read-only QtPdf-based rendering (QPdfDocument has no write/save API at all).
Uses pypdf, a pure-Python library: no external binary to shell out to, and
no separate write-capable Qt module exists for this.
"""
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError


class PdfToolError(Exception):
    pass


def merge_pdfs(input_paths, output_path):
    """Concatenates PDFs in the given order into one new file. Never
    modifies the inputs. Raises PdfToolError with a friendly message on
    any unreadable/encrypted input."""
    if len(input_paths) < 2:
        raise PdfToolError("Select at least two PDFs to merge.")
    writer = PdfWriter()
    for p in input_paths:
        path = Path(p)
        try:
            reader = PdfReader(str(path))
        except PdfReadError as e:
            raise PdfToolError(f"Could not read {path.name}: {e}") from e
        if reader.is_encrypted:
            raise PdfToolError(f"{path.name} is password-protected and can't be merged yet.")
        for page in reader.pages:
            writer.add_page(page)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "wb") as f:
        writer.write(f)
    return str(output)


def _parse_page_ranges(ranges_str, page_count):
    """Parses a string like '1-3,5,8-10' (1-indexed, inclusive) into a
    sorted list of 0-indexed page numbers. Raises PdfToolError on anything
    that doesn't resolve to valid pages -- never silently clamps/drops."""
    pages = []
    for part in ranges_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start, end = (int(x) for x in part.split("-", 1))
            except ValueError as e:
                raise PdfToolError(f'"{part}" is not a valid page range.') from e
        else:
            try:
                start = end = int(part)
            except ValueError as e:
                raise PdfToolError(f'"{part}" is not a valid page number.') from e
        if start < 1 or end > page_count or start > end:
            raise PdfToolError(f'"{part}" is out of range for a {page_count}-page document.')
        pages.extend(range(start - 1, end))
    if not pages:
        raise PdfToolError("Enter at least one page or page range.")
    return sorted(set(pages))


def split_pdf(input_path, output_path, ranges_str):
    """Extracts the given 1-indexed page range(s) from input_path into a
    single new PDF at output_path. Does not modify or delete the input."""
    path = Path(input_path)
    try:
        reader = PdfReader(str(path))
    except PdfReadError as e:
        raise PdfToolError(f"Could not read {path.name}: {e}") from e
    if reader.is_encrypted:
        raise PdfToolError(f"{path.name} is password-protected and can't be split yet.")
    pages = _parse_page_ranges(ranges_str, len(reader.pages))
    writer = PdfWriter()
    for i in pages:
        writer.add_page(reader.pages[i])
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "wb") as f:
        writer.write(f)
    return str(output)


def page_count(input_path):
    try:
        reader = PdfReader(str(input_path))
    except PdfReadError as e:
        raise PdfToolError(f"Could not read {Path(input_path).name}: {e}") from e
    return len(reader.pages)
