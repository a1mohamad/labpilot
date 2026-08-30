from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.ingest._pdf import load_pdf, split_pdf
from labpilot.ingest.errors import LoaderError

PAPERS = Path("data/samples/pdf")


def a_pdf_with_no_text_layer(pages: int = 3) -> bytes:
    """What a scanned PDF is: real pages, and no text operators at all."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(b"3 0 R" for _ in range(pages))
        + b"] /Count "
        + str(pages).encode()
        + b" >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    pdf, offsets = b"%PDF-1.4\n", []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += str(number).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    start = len(pdf)
    pdf += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode()
    return pdf + (
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(start).encode()
        + b"\n%%EOF\n"
    )


@pytest.fixture(scope="module")
def two_column():
    return load_pdf((PAPERS / "two_column.pdf").read_bytes())


def test_a_two_column_paper_reads_in_reading_order(two_column):
    """Measured over 24 real papers: LaTeX writes one whole column and then
    the other, so plain extraction is already correct and no gutter-cutting
    layer is needed."""
    assert "deep residual learning framework" in two_column
    assert "degradation problem" in two_column


def test_a_one_column_paper_reads_too():
    text = load_pdf((PAPERS / "one_column.pdf").read_bytes())

    assert text.startswith("# %% page 1")
    assert "Attention" in text


def test_ligatures_are_folded_so_a_citation_can_match(two_column):
    assert "ﬁ" not in two_column
    assert "ﬂ" not in two_column


def test_every_page_that_carries_text_is_marked(two_column):
    marks = [line for line in two_column.splitlines() if line.startswith("# %% page ")]

    assert marks == [f"# %% page {number}" for number in range(1, 13)]


def test_a_pdf_whose_fonts_carry_glyph_names_is_refused_not_kept_as_nonsense():
    """This file extracts SUCCESSFULLY as '/D8/D6/D3 /DB /CT/CP/CZ'. Nothing
    raises, which is exactly why the check has to exist."""
    with pytest.raises(LoaderError, match="vowel"):
        load_pdf((PAPERS / "type3_garbled.pdf").read_bytes())


def test_a_scanned_pdf_is_refused_and_never_returned_empty():
    with pytest.raises(LoaderError, match="scanned"):
        load_pdf(a_pdf_with_no_text_layer())


@pytest.mark.parametrize(
    "raw", [b"", b"this is plain text", b"\x89PNG\r\n\x1a\n", b"%PDF-1.4\n"]
)
def test_bytes_that_are_not_a_pdf_are_refused_with_our_own_error(raw):
    with pytest.raises(LoaderError):
        load_pdf(raw)


def test_each_page_becomes_its_own_piece(two_column):
    pieces = split_pdf(two_column)

    assert [piece.label for piece in pieces] == [
        f"page {number}" for number in range(1, 13)
    ]


def test_a_piece_points_at_the_lines_it_really_covers(two_column):
    lines = two_column.splitlines()
    for piece in split_pdf(two_column):
        assert piece.text == "\n".join(lines[piece.start_line - 1 : piece.end_line])
