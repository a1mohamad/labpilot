from __future__ import annotations

import io
import re
import unicodedata

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from labpilot.ingest._sections import Mark, to_pieces
from labpilot.ingest.contracts import Piece
from labpilot.ingest.defaults import (
    MIN_PDF_CHARS_PER_PAGE,
    MIN_PDF_WORDS_WITH_VOWELS,
)
from labpilot.ingest.errors import LoaderError

PAGE_MARK = re.compile(r"^# %% page (\d+)$")
WORD = re.compile(r"[A-Za-z]{2,}")
VOWELS = frozenset("aeiouyAEIOUY")


def load_pdf(raw: bytes) -> str:
    pages = _pages(raw)
    blocks: list[str] = []
    body = ""

    for number, page in enumerate(pages, start=1):
        text = _readable(page)
        body += text
        if text:
            blocks.append(f"# %% page {number}\n{text}")

    _refuse_pictures_of_text(body, len(pages))
    _refuse_unmappable_glyphs(body)
    return "\n\n".join(blocks)


def _pages(raw: bytes) -> list[str]:
    # Measured over six kinds of broken input: pypdf raises PdfReadError or a
    # subclass every time, so nothing wider needs catching.
    try:
        reader = PdfReader(io.BytesIO(raw))
        return [page.extract_text() for page in reader.pages]
    except PdfReadError as exc:
        raise LoaderError(f"not a readable PDF: {exc}") from exc


def _readable(page: str) -> str:
    return unicodedata.normalize("NFKC", page).strip()


def _refuse_pictures_of_text(body: str, pages: int) -> None:
    if not pages:
        raise LoaderError("a PDF with no pages")

    density = len(body) / pages
    if density < MIN_PDF_CHARS_PER_PAGE:
        raise LoaderError(
            f"{density:.0f} characters per page across {pages} page(s), under "
            f"the {MIN_PDF_CHARS_PER_PAGE} floor. This is a scanned PDF: it "
            f"holds pictures of text and no text. Reading it needs OCR, which "
            f"does not fit this project's memory budget"
        )


def _refuse_unmappable_glyphs(body: str) -> None:
    # Old dvips PDFs store letters as tiny pictures named /CT, /CZ, /DB, and
    # extraction succeeds returning those names. Real words carry a vowel and
    # glyph names do not. Measured over 24 papers and 596 pages: the broken
    # file scores 0.129, and every good page scores 0.516 or better. Counting
    # words rather than characters is what keeps a table of numbers innocent.
    words = WORD.findall(body)
    if not words:
        return

    real = sum(1 for word in words if VOWELS & set(word)) / len(words)
    if real < MIN_PDF_WORDS_WITH_VOWELS:
        raise LoaderError(
            f"only {real:.0%} of the words contain a vowel, under the "
            f"{MIN_PDF_WORDS_WITH_VOWELS:.0%} floor. The fonts in this PDF "
            f"carry glyph names rather than characters, so the text came out "
            f"as nonsense. Re-export it from a newer tool, or supply the source"
        )


def split_pdf(text: str) -> list[Piece]:
    lines = text.splitlines()
    return to_pieces(lines, _mark_lines(lines))


def _mark_lines(lines: list[str]) -> list[Mark]:
    marks: list[Mark] = []
    for index, line in enumerate(lines):
        match = PAGE_MARK.match(line)
        if match:
            marks.append((index, f"page {match.group(1)}"))

    return marks
