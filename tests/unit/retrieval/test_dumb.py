from __future__ import annotations

from pathlib import Path

from labpilot.ingest import Chunk, chunk_file
from labpilot.retrieval import select
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


def test_each_side_gets_its_own_half():
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
