from __future__ import annotations

import pytest

from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    ModelMismatch,
    UnknownArtifact,
    search,
    write_artifact,
)

pytestmark = pytest.mark.database

MODEL = "codestral-embed"
DIM = 3

# Deliberate geometry, so the expected ORDER is arithmetic and not a guess.
# The query is [1, 0, 0]; cosine distance grows as a vector turns away from it.
#   0  same direction        distance 0.0   score  1.0
#   1  a small turn          distance ~0.1  score ~0.9
#   2  at a right angle      distance 1.0   score  0.0
#   3  the opposite way      distance 2.0   score -1.0
# Sorting the WRONG way (desc) returns 3, 2, 1, 0 - the least relevant first.
QUERY = (1.0, 0.0, 0.0)
PLACES = {
    0: (1.0, 0.0, 0.0),
    1: (0.9, 0.4359, 0.0),
    2: (0.0, 1.0, 0.0),
    3: (-1.0, 0.0, 0.0),
}


def artifact(**overrides) -> ArtifactRecord:
    fields = {
        "id": "s1",
        "name": "train.py",
        "side": "B",
        "embedding_model": MODEL,
        "dim": DIM,
    }
    return ArtifactRecord(**{**fields, **overrides})


def chunk(index: int, vector: tuple[float, ...]) -> ChunkRecord:
    return ChunkRecord(
        chunk_index=index,
        text=f"line {index}",
        source="train.py",
        start_line=index * 10,
        end_line=index * 10 + 5,
        header=f"[train.py - part {index}]",
        vector=vector,
    )


def stored(db, **overrides) -> ArtifactRecord:
    record = artifact(**overrides)
    write_artifact(db, record, [chunk(i, v) for i, v in PLACES.items()])
    return record


def test_the_nearest_chunk_comes_back_first(db):
    stored(db)

    hits = search(db, "s1", QUERY, model=MODEL)

    assert [hit.chunk_index for hit in hits] == [0, 1, 2, 3]


def test_the_scores_fall_as_the_chunks_turn_away(db):
    stored(db)

    scores = [hit.score for hit in search(db, "s1", QUERY, model=MODEL)]

    assert scores == sorted(scores, reverse=True)
    assert scores[0] == pytest.approx(1.0, abs=1e-6)
    assert scores[2] == pytest.approx(0.0, abs=1e-6)
    assert scores[3] == pytest.approx(-1.0, abs=1e-6)


def test_a_hit_carries_the_line_numbers_a_citation_needs(db):
    stored(db)

    best = search(db, "s1", QUERY, model=MODEL)[0]

    assert (best.text, best.source) == ("line 0", "train.py")
    assert (best.start_line, best.end_line) == (0, 5)
    assert best.header == "[train.py - part 0]"


def test_only_the_named_artifact_is_searched(db):
    stored(db, id="mine")
    stored(db, id="other")

    hits = search(db, "mine", QUERY, model=MODEL)

    assert len(hits) == len(PLACES)


def test_the_limit_caps_how_many_come_back(db):
    stored(db)

    hits = search(db, "s1", QUERY, model=MODEL, limit=2)

    assert [hit.chunk_index for hit in hits] == [0, 1]


@pytest.mark.parametrize("limit", [0, -1])
def test_a_limit_that_returns_nothing_is_a_caller_bug(db, limit):
    # Store it first, so the limit guard is the ONLY thing that can refuse.
    # Without that, a missing artifact raises instead and the test passes for
    # the wrong reason.
    stored(db)

    with pytest.raises(ValueError, match="limit"):
        search(db, "s1", QUERY, model=MODEL, limit=limit)


def test_a_query_from_a_different_model_is_refused(db):
    stored(db)

    with pytest.raises(ModelMismatch, match="gemini-embedding-001"):
        search(db, "s1", QUERY, model="gemini-embedding-001")


def test_a_query_of_the_wrong_width_is_refused(db):
    stored(db)

    with pytest.raises(ValueError, match="dimensions"):
        search(db, "s1", (1.0, 0.0), model=MODEL)


def test_an_unknown_artifact_is_refused_rather_than_returning_nothing(db):
    # Empty and absent are different facts. Returning () for an artifact that
    # was never stored reads as "nothing matched", and the corpus is missing.
    with pytest.raises(UnknownArtifact, match="nope"):
        search(db, "nope", QUERY, model=MODEL)
