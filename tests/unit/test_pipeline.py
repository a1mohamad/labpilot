from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.ingest import chunk_file
from labpilot.retrieval import INPUT_BUDGET, select
from labpilot.tokens import estimate_tokens

SAMPLES = Path("data/samples/quora_siamese")


@pytest.fixture(scope="module")
def picked():
    chunks = chunk_file(
        SAMPLES / "A_paper.md", side="A", artifact_id="quora"
    ) + chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="quora")
    return select(chunks)


def test_the_pipeline_produces_a_prompt_that_fits_the_budget(picked):
    assert picked
    assert sum(estimate_tokens(chunk.embed_text) for chunk in picked) <= INPUT_BUDGET


def test_the_pipeline_keeps_both_sides(picked):
    assert {chunk.side for chunk in picked} == {"A", "B"}


def test_every_selected_chunk_can_still_be_checked_against_its_file(picked):
    sources = {
        name: (SAMPLES / name).read_text(encoding="utf-8").splitlines()
        for name in ("A_paper.md", "B_train.py")
    }
    for chunk in picked:
        lines = sources[chunk.source]
        cited = "\n".join(lines[chunk.start_line - 1 : chunk.end_line])
        assert chunk.text in cited


def test_the_pipeline_gives_the_same_answer_every_time():
    def run():
        chunks = chunk_file(
            SAMPLES / "A_paper.md", side="A", artifact_id="quora"
        ) + chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="quora")
        return tuple(chunk.header for chunk in select(chunks))

    assert run() == run()
