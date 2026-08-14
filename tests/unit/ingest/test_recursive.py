from __future__ import annotations

import pytest

from labpilot.ingest._recursive import split_recursive
from labpilot.ingest.defaults import MAX_CHUNK_TOKENS
from labpilot.tokens import estimate_tokens

PARAGRAPHS = [f"paragraph {i:02d} " + "word " * 60 for i in range(40)]
LONG_TEXT = "\n\n".join(PARAGRAPHS)


def _lines_of(text: str, piece) -> str:
    return "\n".join(text.splitlines()[piece.start_line - 1 : piece.end_line])


def test_text_under_the_cap_is_one_piece():
    pieces = split_recursive("hello world")
    assert len(pieces) == 1
    assert pieces[0].text == "hello world"


@pytest.mark.parametrize("text", ["", "   ", "\n\n\t\n"])
def test_blank_text_yields_no_pieces(text):
    assert split_recursive(text) == []


def test_no_piece_exceeds_the_hard_cap():
    pieces = split_recursive(LONG_TEXT)
    assert len(pieces) > 1
    assert all(estimate_tokens(p.text) <= MAX_CHUNK_TOKENS for p in pieces)


def test_line_numbers_point_at_the_text():
    for piece in split_recursive(LONG_TEXT):
        assert piece.text in _lines_of(LONG_TEXT, piece)


def test_consecutive_pieces_overlap():
    pieces = split_recursive(LONG_TEXT)
    assert all(
        nxt.start_line <= cur.end_line
        for cur, nxt in zip(pieces, pieces[1:], strict=False)
    )


def test_a_word_is_never_cut_in_half():
    assert all(p.text.endswith("word") for p in split_recursive(LONG_TEXT))


def test_text_with_no_separators_still_splits_under_the_cap():
    pieces = split_recursive("x" * 20_000)
    assert len(pieces) > 1
    assert all(estimate_tokens(p.text) <= MAX_CHUNK_TOKENS for p in pieces)
