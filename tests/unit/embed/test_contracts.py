from __future__ import annotations

import pytest

from labpilot.embed.contracts import EmbeddingBatch


def test_a_batch_rejects_a_vector_of_the_wrong_width():
    with pytest.raises(ValueError, match="3 dimensions"):
        EmbeddingBatch(
            vectors=((0.1, 0.2, 0.3), (0.4, 0.5)),
            model="mistral-embed",
            dim=3,
            prompt_tokens=7,
        )


def test_a_batch_rejects_being_empty():
    with pytest.raises(ValueError, match="at least one vector"):
        EmbeddingBatch(
            vectors=(),
            model="mistral-embed",
            dim=3,
            prompt_tokens=0,
        )


def test_a_batch_accepts_vectors_that_all_match_the_declared_width():
    batch = EmbeddingBatch(
        vectors=((0.1, 0.2, 0.3), (0.4, 0.5, 0.6)),
        model="mistral-embed",
        dim=3,
        prompt_tokens=7,
    )

    assert batch.dim == 3
    assert len(batch.vectors) == 2
