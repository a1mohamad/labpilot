from __future__ import annotations

from collections.abc import Sequence

# How far ahead the best hit must be before reranking is not worth paying for.
#
# None means THE GATE IS OFF, and that is deliberate rather than unfinished: a
# threshold in this project is CALIBRATED, never chosen, exactly as the
# correspondence gate's threshold must be. Slice 6 measured the margin on 124
# query-runs and the answer is recorded in CLAUDE.md; until a number is earned,
# shipping `None` means "always rerank", which is the behaviour that cannot be
# silently wrong.
SKIP_MARGIN: float | None = None


def margin(scores: Sequence[float]) -> float:
    """How far the best hit leads the runner-up.

        m = s(1) - s(2)

    The two BEST scores, not the first two in the sequence. Retrieval does
    return them sorted today, but a gate that silently depends on its caller's
    ordering is a gate that breaks the first time somebody fuses two rankings
    and forgets - and it breaks by quietly comparing the wrong pair, with no
    error anywhere.

    One score means nothing leads anything, so the margin is 0.0: there is no
    runner-up to be ahead of, and claiming a large lead would make the gate
    skip precisely when it has the least evidence.
    """
    if len(scores) < 2:
        return 0.0
    best, second = sorted(scores, reverse=True)[:2]
    return best - second


def should_rerank(
    scores: Sequence[float], *, skip_margin: float | None = SKIP_MARGIN
) -> bool:
    """Is the winner already obvious enough to save the call?

    The signal is free: the similarity matrix holds every score, so the gate
    costs arithmetic and no provider is touched. The literature puts the saving
    at 15-80% of rerank compute, and reports something more interesting than
    the saving - reranking can make results WORSE when the first stage was
    already confident and correct.

    Fewer than two hits cannot be reordered at all, so there is nothing to buy.
    """
    if len(scores) < 2:
        return False
    if skip_margin is None:
        return True
    return margin(scores) <= skip_margin
