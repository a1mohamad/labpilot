import math
from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.embed import MIGRATION
from labpilot.ingest import chunk_file

load_dotenv()

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples" / "quora_siamese"

CODE = chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="code")[3].embed_text
CLAIM = chunk_file(SAMPLES / "A_paper.md", side="A", artifact_id="paper")[0].embed_text

# Google answers 400 FAILED_PRECONDITION - "User location is not supported" from
# this account's connection as of 2026-08-20, on generation and embedding alike.
# xfail(strict=False), never deleted: the day the location is fixed this flips to
# XPASS, which is the signal we want and would otherwise never arrive.
BLOCKED = {"Gemini Embedding 001"}


def _case(embedder):
    marks = (
        [pytest.mark.xfail(reason="user location is not supported", strict=False)]
        if embedder.name in BLOCKED
        else []
    )
    return pytest.param(embedder, marks=marks, id=embedder.model)


@pytest.mark.smoke
@pytest.mark.parametrize("embedder", [_case(e) for e in MIGRATION])
def test_every_embedder_is_alive_and_its_declared_dimension_is_still_true(embedder):
    batch = embedder.embed([CODE, CLAIM])

    assert len(batch.vectors) == 2
    assert batch.dim == embedder.dim

    for vector in batch.vectors:
        assert len(vector) == embedder.dim
        assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)
