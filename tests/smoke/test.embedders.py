import math

import pytest
from dotenv import load_dotenv

from labpilot.embed import MIGRATION

load_dotenv()

SAMPLE = "def train(model, loader):\n    for batch in loader:\n        step(batch)"
CLAIM = "the vocabulary is capped at the 20,000 most frequent tokens"


@pytest.mark.smoke
@pytest.mark.parametrize("embedder", MIGRATION, ids=lambda e: e.model)
def test_every_embedder_is_alive_and_its_declared_dimension_is_still_true(embedder):
    batch = embedder.embed([SAMPLE, CLAIM])

    assert len(batch.vectors) == 2
    assert batch.dim == embedder.dim
    assert batch.prompt_tokens > 0

    for vector in batch.vectors:
        assert len(vector) == embedder.dim
        assert math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0)
