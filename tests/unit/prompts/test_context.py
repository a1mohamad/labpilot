from __future__ import annotations

from labpilot.ingest import Chunk
from labpilot.prompts import build_context


def _chunk(side: str, text: str, header: str) -> Chunk:
    return Chunk(
        text=text,
        source="a.py",
        start_line=1,
        end_line=1,
        side=side,
        artifact_id="t",
        chunk_index=0,
        header=header,
    )


def test_every_chunk_text_reaches_the_prompt():
    chunks = (_chunk("A", "alpha", "[h1]"), _chunk("B", "beta", "[h2]"))
    context = build_context(chunks)
    assert "alpha" in context
    assert "beta" in context


def test_every_header_reaches_the_prompt():
    context = build_context((_chunk("B", "beta", "[b.py · lines 1-1]"),))
    assert "[b.py · lines 1-1]" in context


def test_side_a_comes_before_side_b():
    chunks = (_chunk("B", "beta", "[h2]"), _chunk("A", "alpha", "[h1]"))
    context = build_context(chunks)
    assert context.index("alpha") < context.index("beta")


def test_no_chunks_gives_an_empty_string():
    assert build_context(()) == ""
