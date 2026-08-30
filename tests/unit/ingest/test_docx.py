from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from labpilot.ingest._docx import load_docx
from labpilot.ingest.defaults import MAX_DOCX_XML_BYTES
from labpilot.ingest.errors import LoaderError

PAPER = Path("data/samples/docx/ddos_ensemble.docx")


def a_docx(document_xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def wrapped(body: str) -> str:
    return (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        f'wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    )


@pytest.fixture(scope="module")
def paper():
    return load_docx(PAPER.read_bytes())


def test_a_real_word_paper_reads(paper):
    assert "DDoS" in paper
    assert "ensemble" in paper.lower()


def test_runs_inside_a_paragraph_are_joined_without_a_space(paper):
    """This paragraph really begins with the runs 'T' then 'his paper'.
    Join with a space and it becomes 'T his paper'."""
    assert "This paper Includes" in paper
    assert "T his paper" not in paper


def test_a_line_split_across_fifteen_runs_comes_back_whole(paper):
    assert "train_test_split (X,Y, test_size = 40% )" in paper


def test_paragraphs_are_separated_by_a_blank_line(paper):
    # "\n\n" is split_recursive's second separator, so the blank line is what
    # makes the fallback break on a paragraph instead of mid-sentence.
    assert "\n\n" in paper
    assert not paper.startswith("\n")


def test_a_tab_is_kept_so_two_table_cells_do_not_fuse():
    body = "<w:p><w:r><w:t>Name</w:t><w:tab/><w:t>Value</w:t></w:r></w:p>"

    assert load_docx(a_docx(wrapped(body))) == "Name\tValue"


@pytest.mark.parametrize(
    "raw", [b"", b"hello there", b"\x89PNG\r\n\x1a\n", b"%PDF-1.4\n"]
)
def test_bytes_that_are_not_a_zip_are_refused(raw):
    with pytest.raises(LoaderError, match="ZIP"):
        load_docx(raw)


def test_a_zip_that_is_not_a_word_file_is_refused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<x/>")

    with pytest.raises(LoaderError, match="word/document.xml"):
        load_docx(buffer.getvalue())


def test_broken_xml_is_refused():
    with pytest.raises(LoaderError, match="XML"):
        load_docx(a_docx("<w:p><unclosed>"))


def test_a_decompression_bomb_is_refused_before_it_is_unpacked():
    """A .docx is a ZIP. Measured: 48KB of crafted archive expands to 50MB,
    which is fatal on a 512MB box. The header carries the size, so nothing
    has to be decompressed to find out."""
    bomb = a_docx("A" * 20_000_000)
    assert 20_000_000 > MAX_DOCX_XML_BYTES, "must exceed the real limit"
    assert len(bomb) < 500_000, "the point is that the ARCHIVE stays small"

    with pytest.raises(LoaderError, match="bomb"):
        load_docx(bomb)
