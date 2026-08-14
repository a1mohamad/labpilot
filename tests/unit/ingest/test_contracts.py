from __future__ import annotations

import pytest

from labpilot.ingest.contracts import Chunk


def _chunk(**overrides) -> Chunk:
    fields = dict(
        text="x = 1",
        source="a.py",
        start_line=1,
        end_line=1,
        side="B",
        artifact_id="q",
        chunk_index=0,
    )
    return Chunk(**{**fields, **overrides})


def test_embed_text_prepends_the_header():
    chunk = _chunk(header="[a.py · line 1]")
    assert chunk.embed_text == "[a.py · line 1]\nx = 1"


def test_a_side_outside_a_and_b_is_rejected():
    with pytest.raises(ValueError, match="side must be"):
        _chunk(side="ZZZ")


def test_embed_text_is_the_text_alone_when_there_is_no_header():
    assert _chunk().embed_text == "x = 1"
