from __future__ import annotations

from pathlib import Path

import pytest

from labpilot.ingest import Chunk, chunk_file
from labpilot.ingest.defaults import MAX_CHUNK_TOKENS
from labpilot.retrieval import INPUT_BUDGET, LABEL_TOKENS, SIDE_SHARE, SIDES, select
from labpilot.tokens import estimate_tokens

SAMPLES = Path("data/samples/quora_siamese")


def _chunk(index: int, side: str, words: int = 100) -> Chunk:
    return Chunk(
        text=" ".join(["word"] * words),
        source="a.py" if side == "B" else "a.md",
        start_line=1,
        end_line=1,
        side=side,
        artifact_id="t",
        chunk_index=index,
    )


def _pair(count: int = 10, words: int = 100) -> tuple[Chunk, ...]:
    return tuple(
        _chunk(index, side, words) for index, side in enumerate(["A", "B"] * count)
    )


def _cost(chunks: tuple[Chunk, ...]) -> int:
    return sum(estimate_tokens(chunk.embed_text) for chunk in chunks)


def test_it_never_goes_over_the_budget():
    picked = select(_pair(), budget=600)
    assert _cost(picked) <= 600


def test_each_side_gets_its_own_half_when_both_want_more():
    picked = select(_pair(), budget=600)
    a_side = tuple(chunk for chunk in picked if chunk.side == "A")
    b_side = tuple(chunk for chunk in picked if chunk.side == "B")
    assert _cost(a_side) <= 300
    assert _cost(b_side) <= 300


def test_it_takes_from_both_sides():
    picked = select(_pair(), budget=600)
    assert {chunk.side for chunk in picked} == {"A", "B"}


def test_no_chunk_is_picked_twice():
    picked = select(_pair())
    assert len({id(chunk) for chunk in picked}) == len(picked)


def test_a_budget_too_small_for_one_chunk_picks_nothing():
    assert select(_pair(), budget=2) == ()


def test_no_chunks_in_gives_no_chunks_out():
    assert select((), budget=1000) == ()


def test_everything_is_kept_when_it_all_fits():
    chunks = _pair(count=2, words=10)
    assert set(select(chunks, budget=20_000)) == set(chunks)


def test_the_result_is_grouped_by_side():
    sides = [chunk.side for chunk in select(_pair(), budget=600)]
    assert sides == sorted(sides)


def test_on_the_real_pair_it_drops_chunks():
    chunks = chunk_file(
        SAMPLES / "B_train.py", side="B", artifact_id="quora"
    ) + chunk_file(SAMPLES / "A_paper.md", side="A", artifact_id="quora")
    picked = select(chunks)
    assert len(picked) < len(chunks)


def _sized(side: str, index: int, words: int) -> Chunk:
    """A chunk whose cost is controlled, so the arithmetic in a test is exact."""
    return Chunk(
        text=" ".join(["word"] * words),
        source="f.py",
        start_line=index,
        end_line=index,
        side=side,
        artifact_id="t",
        chunk_index=index,
        header="[f.py]",
    )


def _by_side(picked: tuple[Chunk, ...]) -> dict[str, int]:
    return {side: sum(1 for c in picked if c.side == side) for side in SIDES}


def test_a_small_side_does_not_waste_its_half():
    """The measured flaw the fixed 50/50 split had, and the whole point of pass 2.

    On the sample pair it sent 14,273 tokens of a 20,000 budget: side B filled
    its half while side A needed only 4,273, and the remainder was thrown away
    rather than given to the side that still had chunks.
    """
    chunks = tuple(
        [_sized("A", i, 50) for i in range(3)]
        + [_sized("B", i, 300) for i in range(60)]
    )

    picked = _by_side(select(chunks, budget=20_000))

    assert picked["A"] == 3, "a small side takes everything it has"
    assert picked["B"] > 30, "and the leftover flows to the side that wants more"


def test_neither_side_is_privileged():
    """THE DECISION OF 2026-09-14, and the test that would catch it being undone.

    CLAUDE.md carried "fill A before B" for a month. It was overturned because
    it leaves A UNCAPPED - a large reference would take the whole budget and B
    would get zero - and because half the scenarios are code-vs-code, where a
    side preference biases the report by UPLOAD ORDER.

    So the rule must be a mirror: swap which side is large and the answer must
    swap with it, exactly. Any preference for a slot shows up here as an
    asymmetry and nowhere else.
    """
    big_a = tuple(
        [_sized("A", i, 300) for i in range(60)]
        + [_sized("B", i, 50) for i in range(3)]
    )
    big_b = tuple(
        [_sized("A", i, 50) for i in range(3)]
        + [_sized("B", i, 300) for i in range(60)]
    )

    left = _by_side(select(big_a, budget=20_000))
    right = _by_side(select(big_b, budget=20_000))

    assert left["A"] == right["B"]
    assert left["B"] == right["A"]


def test_neither_side_can_starve_the_other():
    """When BOTH sides want more than their share, both still get one.

    This is the case "A before B" got wrong: it would hand A everything and
    leave B with nothing, and a comparison with one side is not a comparison.
    """
    chunks = tuple(
        [_sized("A", i, 300) for i in range(60)]
        + [_sized("B", i, 300) for i in range(60)]
    )

    picked = _by_side(select(chunks, budget=20_000))

    assert picked["A"] > 0
    assert picked["B"] > 0
    assert abs(picked["A"] - picked["B"]) <= 1, "equal shares, give or take rounding"


def test_a_single_side_gets_the_whole_budget():
    """The 1-artifact mode - summarize, find_bugs - where there is no other side.

    Half the budget would be thrown away here, which is what the fixed split
    did. An absent side needs nothing, so all of it flows over.
    """
    chunks = tuple(_sized("B", i, 300) for i in range(60))

    picked = select(chunks, budget=20_000)

    assert sum(_cost((c,)) for c in picked) > 19_000


def test_a_chunk_costs_its_label_as_well_as_its_text():
    """The charge step 2 removed from reserve() and moved here.

    reserve() used to add a `B-1234  ` label for EVERY chunk in the corpus
    though only the selected handful is printed - 24,899 tokens of a 26,000
    budget on an 8,333-chunk upload. Here it is charged per chunk ACTUALLY
    TAKEN, which is the only place that number is knowable.

    The budget below pays for exactly one chunk's text and nothing more, so a
    selector that forgets the label takes one chunk and one that charges it
    takes none.
    """
    chunk = _sized("A", 0, 50)
    text_only = estimate_tokens(chunk.embed_text)

    assert select((chunk,), budget=text_only) == ()
    assert select((chunk,), budget=text_only + LABEL_TOKENS) == (chunk,)


def test_the_shares_can_never_add_up_to_more_than_the_budget():
    """SIDE_SHARE is a knob slice 8 will sweep, and one wrong value overflows.

    Each side is allotted `budget * SIDE_SHARE` before any leftover moves, so
    anything above 1 / len(SIDES) lets the two halves exceed the whole - and
    the prompt would be over budget with no error anywhere.
    """
    assert SIDE_SHARE * len(SIDES) <= 1


def test_a_chunk_at_the_hard_cap_still_fits_a_single_side():
    """Why `_fill` may STOP at a chunk that does not fit instead of skipping on.

    It can only ever lose chunks near the END of a side's list - never the
    best one - and that holds only while one chunk is small against one side's
    share. Two constants in two packages have to stay in that relationship,
    and nothing else checks it.
    """
    share = INPUT_BUDGET * SIDE_SHARE

    assert MAX_CHUNK_TOKENS < share / 10, "a chunk must be small against a side's share"


def test_a_negative_budget_is_a_callers_bug():
    """A caller's bug and a provider's failure stay different exceptions.

    Nothing recovers from a negative budget, so it must crash rather than
    quietly return no chunks and read as "nothing was relevant".
    """
    with pytest.raises(ValueError, match="negative"):
        select((_sized("A", 0, 50),), budget=-1)
