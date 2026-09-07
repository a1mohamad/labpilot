from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

# Measured 2026-09-07: two corpora, two embedders, 62 queries, 82 settings.
# The TEXTBOOK defaults are k=60 and w=1.0, and that is the WORST row in our
# own table -- the only setting that loses recall@50. A small k with a small
# keyword weight is the region that is never worse than vector alone on any
# run: wRRF k=5 w=0.15 gained r@5 +0.020 and MRR +0.010 while r@50 held.
RRF_K = 5
RRF_WEIGHTS = (1.0, 0.15)


def weighted_rrf(
    *orders: Sequence[int],
    k: int = RRF_K,
    weights: Sequence[float] = RRF_WEIGHTS,
) -> tuple[int, ...]:
    """Fuse several rankings of chunk_index into one.

    Reciprocal rank fusion scores by PLACE, never by the rankers' own scores,
    which is the point: a cosine similarity and a BM25 score are on different
    scales and adding them directly is meaningless.

        score(chunk) = sum over rankers of  weight / (k + place)

    This takes and returns chunk_index only. retrieval/ is core and may not
    import an adapter, so it cannot see SearchHit -- and that constraint gives
    the right shape anyway: fusion is arithmetic over rankings and needs to
    know nothing about rows, databases or embedders.
    """
    if k < 1:
        raise ValueError(f"k must be positive, got {k}")
    if len(weights) != len(orders):
        raise ValueError(
            f"got {len(orders)} ranking(s) and {len(weights)} weight(s): "
            f"every ranking needs exactly one weight"
        )

    score: dict[int, float] = defaultdict(float)
    for order, weight in zip(orders, weights, strict=True):
        for place, chunk_index in enumerate(order, 1):
            score[chunk_index] += weight / (k + place)

    return tuple(
        chunk_index
        for chunk_index, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))
    )
