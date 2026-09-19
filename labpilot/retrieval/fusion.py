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

# THE SHIPPED METHOD, measured 2026-09-19 over 20 corpora and 423 queries:
# `score a=0.85` was #1 of 51 settings in a real search, not a re-test of v2's
# winner. Weight on the DENSE channel, so the keyword side can reorder and
# rescue but never take over.
#
#   gains >= 1 query on   5 corpora
#   loses >= 1 query on   0 corpora        <- the property a permanently-on
#   net   +8.7 queries MRR, +6.0 r@50         channel has to have
#
# docs/slice8v3/DECISIONS.md rows 1-4.
SCORE_ALPHA = 0.85


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


def _minmax(scored: Sequence[tuple[int, float]]) -> dict[int, float]:
    """Rescale one ranker's scores to [0, 1].

    This is the step RRF exists to AVOID: a cosine similarity and a BM25 score
    are on different scales, so they cannot be added until both are rescaled -
    and the rescaling is then one more thing that can be wrong.

    A channel whose scores are all equal collapses to 1.0 rather than to 0.0.
    That case is real: BM25 returns a flat list when every hit holds the query
    terms equally often, and mapping it to zero would silently delete the
    channel exactly when it agreed with itself most strongly.
    """
    if not scored:
        return {}

    values = [score for _, score in scored]
    low, high = min(values), max(values)
    if high == low:
        return {index: 1.0 for index, _ in scored}

    return {index: (score - low) / (high - low) for index, score in scored}


def score_fusion(
    dense: Sequence[tuple[int, float]],
    sparse: Sequence[tuple[int, float]],
    *,
    alpha: float = SCORE_ALPHA,
) -> tuple[int, ...]:
    """Fuse two rankings by their NORMALISED scores, not by their places.

        score(chunk) = alpha * dense_norm  +  (1 - alpha) * sparse_norm

    A chunk found by only one channel keeps that channel's contribution and
    scores 0.0 for the other, so a keyword-only hit can still enter the window.
    That is the whole point of the rescue: `D2` is the worked example - the
    constant CLIP_NORM = 1.5 sat at place 46 on cosine and 4 on BM25.

    Takes and returns chunk_index only. retrieval/ is core and may not import
    an adapter, so it cannot see SearchHit - and the constraint gives the right
    shape anyway: fusion is arithmetic over rankings and needs to know nothing
    about rows, databases or embedders.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha is a weight on the dense channel, got {alpha}")

    hot, cold = _minmax(dense), _minmax(sparse)
    total = {
        index: alpha * hot.get(index, 0.0) + (1 - alpha) * cold.get(index, 0.0)
        for index in set(hot) | set(cold)
    }

    # Ties break on chunk_index, so the same two inputs always give the same
    # order. `temperature: 0` is worth nothing if retrieval is unstable.
    return tuple(
        index for index, _ in sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))
    )
