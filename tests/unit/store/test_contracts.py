from __future__ import annotations

import pytest

from labpilot.store import ArtifactRecord


def record(**overrides):
    fields = dict(
        id="a1", name="paper.pdf", side="A", embedding_model="codestral-embed", dim=1536
    )
    return ArtifactRecord(**{**fields, **overrides})


@pytest.mark.parametrize("side", ["C", "a", "b", "", "AB"])
def test_a_side_that_is_not_a_or_b_is_refused(side):
    with pytest.raises(ValueError, match="side"):
        record(side=side)


@pytest.mark.parametrize("dim", [0, -1])
def test_a_dimension_that_is_not_positive_is_refused(dim):
    with pytest.raises(ValueError, match="dim"):
        record(dim=dim)
