import pytest

from labpilot.ingest import Chunk
from labpilot.prompts import build_context


def _chunk(side: str, index: int, text: str = "body") -> Chunk:
    return Chunk(
        text=text,
        source="f.py",
        start_line=1,
        end_line=1,
        side=side,
        artifact_id="a",
        chunk_index=index,
        header="[f.py · lines 1-1]",
    )


def test_every_chunk_appears_in_the_outline():
    chunks = (_chunk("A", 0), _chunk("A", 1))

    context = build_context(chunks, (chunks[0],))

    assert "A-0" in context
    assert "A-1" in context


def test_only_selected_chunks_show_their_text():
    kept = _chunk("A", 0, text="this was kept")
    dropped = _chunk("A", 1, text="this was dropped")

    context = build_context((kept, dropped), (kept,))

    assert "this was kept" in context
    assert "this was dropped" not in context


def test_a_dropped_chunk_is_marked_in_the_outline():
    chunks = (_chunk("A", 0), _chunk("A", 1))

    context = build_context(chunks, (chunks[0],))

    assert "A-1  text NOT included" in context


def test_a_side_with_nothing_selected_says_so():
    chunks = (_chunk("A", 0), _chunk("B", 0))

    context = build_context(chunks, (chunks[0],))

    assert "(no part of this side was included)" in context


def test_a_side_with_no_chunks_is_left_out():
    chunks = (_chunk("A", 0),)

    context = build_context(chunks, chunks)

    assert "SIDE B" not in context


def test_a_selected_chunk_that_is_not_in_chunks_is_our_bug():
    chunks = (_chunk("A", 0),)
    stranger = _chunk("A", 9)

    with pytest.raises(ValueError):
        build_context(chunks, (stranger,))
