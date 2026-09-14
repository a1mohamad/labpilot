from __future__ import annotations

from collections.abc import Sequence

from labpilot.ingest import Chunk
from labpilot.tokens import estimate_tokens

SIDES = ("A", "B")

# The evidence budget, and it is OURS - no provider enforces it.
#
# Far below every tier's context window on purpose. Tokens-per-minute binds
# before context does, and a focused prompt beats a padded one because
# attention spreads and the important lines get buried. Measured: stuffing all
# 96 chunks of the sample pair scored 11 of 18 against this selector's 10, so
# more evidence is nowhere near proportional to more findings.
INPUT_BUDGET = 20_000

# How much of the budget ONE side may claim before the other has had its turn.
#
# A KNOB, not a law, and slice 8 sweeps it the way it will sweep the retrieval
# window: for now half, and it may decide that of a 50-document limit, 30 go to
# each side. It must never exceed 1 / len(SIDES), or the shares overlap and the
# two halves can add up to more than the budget - pinned by a test.
SIDE_SHARE = 0.5

# What a chunk costs BEYOND its own text: the `B-1234  ` label the prompt
# prints above it. About 3 tokens, and stable across realistic corpus sizes -
# "B-9  " is 2, "B-12345  " is 3.
#
# It used to be charged in reserve(), for EVERY chunk in the corpus instead of
# the selected handful. Measured 2026-09-14 on an 8,333-chunk upload that was
# 24,899 tokens of a 26,000 budget - 96% held for labels that would never be
# printed, which let 4 chunks through instead of 266. It belongs here, where
# the chunks are actually chosen.
LABEL_TOKENS = 3


def select(
    chunks: tuple[Chunk, ...], *, budget: int = INPUT_BUDGET
) -> tuple[Chunk, ...]:
    """Fill the prompt from both sides, and let unspent room flow over.

    NEITHER SIDE IS PRIVILEGED, and that is a decision rather than an accident.
    CLAUDE.md carried "fill A before B" from 2026-08-14 until it was overturned
    on 2026-09-14, for four reasons:

        its argument covers `verify` only. Session 10 measured FIVE findings
        from side B alone that seventeen comparison runs never found, and
        seven of the nineteen have no A anchor at all.

        half the scenarios have no reference. Code-vs-code is symmetric, and
        there a side preference biases the report by UPLOAD ORDER.

        the slots are the user's choice - POST /artifacts takes `side` as a
        form field and nothing infers it. Privileging A privileges a habit.

        and the fatal one: "A before B" leaves A UNCAPPED, so a 30,000-token
        reference takes the whole budget and B gets zero. A comparison with
        one side is not a comparison.

    The old rule was never load-bearing anyway: when A fits, it and this rule
    give the IDENTICAL answer. They differ only when A does not fit, which is
    precisely the case its own note said does not arise.

    What the fixed 50/50 split really cost was the leftover - measured, 14,273
    tokens sent of a 20,000 budget, because B filled its half while A needed
    only 4,273 and the remainder was thrown away. So:

        pass 1   each side takes up to its share
        pass 2   whatever is unspent flows to the side that still wants more

    ONLY ONE SIDE CAN EVER WANT MORE after pass 1, which is what keeps pass 2
    fair without a tie-break. A side is capped at `share` only if it needed at
    least `share`; if both did, the two allotments already fill the budget and
    there is nothing left to give.
    """

    if budget < 0:
        raise ValueError(f"budget most not be negative, got {budget}")

    share = int(budget * SIDE_SHARE)
    on_side = {side: [c for c in chunks if c.side == side] for side in SIDES}
    needed = {side: sum(map(_cost, on_side[side])) for side in SIDES}

    allotted = {side: min(needed[side], share) for side in SIDES}
    leftover = budget - sum(allotted.values())

    for side in SIDES:
        if leftover > 0 and needed[side] > allotted[side]:
            allotted[side] += leftover
            leftover = 0

    picked: list[Chunk] = []
    for side in SIDES:
        picked.extend(_fill(on_side[side], allotted[side]))

    return tuple(picked)


def _fill(chunks: Sequence[Chunk], room: int) -> list[Chunk]:
    """Take chunks in order until one does not fit, then STOP.

    Stop rather than skip ahead to a smaller one. After the ask path is wired
    these arrive RANKED best-first, so skipping would trade a more relevant
    chunk for a less relevant but smaller one - and this project has already
    measured that more evidence is not more findings.

    The waste is bounded and small: a chunk is capped at MAX_CHUNK_TOKENS, so
    at most ~510 tokens of a ~12,600 half-budget go unused, about 4%. The BEST
    chunk can never be lost this way, because the first one always fits by a
    factor of twenty-five.
    """
    picked: list[Chunk] = []
    spent = 0
    for chunk in chunks:
        cost = _cost(chunk)
        if spent + cost > room:
            break
        picked.append(chunk)
        spent += cost

    return picked


def _cost(chunk: Chunk) -> int:
    """What this chunk really costs the prompt: its text PLUS its id label."""
    return estimate_tokens(chunk.embed_text) + LABEL_TOKENS
