"""The two reads the planner's map is built from - headers, and a per-file score.

Both run BEFORE any search, which is the whole point: the planner decides what
to search for, so it cannot start from retrieved chunks.
"""

from __future__ import annotations

import pytest

from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    ModelMismatch,
    UnknownArtifact,
    file_scores,
    read_headers,
    write_artifact,
)

pytestmark = pytest.mark.database

MODEL = "codestral-embed"
DIM = 3
QUERY = (1.0, 0.0, 0.0)

# ids start at 100, never 0 - a fixture numbered from zero cannot tell a
# chunk_index from a row position.
FIRST_ID = 100


def artifact(**overrides) -> ArtifactRecord:
    fields = {
        "id": "m1",
        "name": "repo",
        "side": "B",
        "embedding_model": MODEL,
        "dim": DIM,
    }
    return ArtifactRecord(**{**fields, **overrides})


def chunk(index: int, source: str, vector, header: str = "") -> ChunkRecord:
    return ChunkRecord(
        chunk_index=index,
        text=f"the text of chunk {index}, which the map must never carry",
        header=header or f"[{source} · def f{index} · lines {index}-{index + 5}]",
        source=source,
        start_line=index,
        end_line=index + 5,
        vector=vector,
    )


# train.py has one chunk pointing AT the query and one at a right angle, so its
# BEST is 1.0 and its MEAN is 0.5. model.py points away. The two readings
# disagree about train.py, which is what lets a test tell max from mean.
CHUNKS = [
    chunk(FIRST_ID, "train.py", (1.0, 0.0, 0.0)),
    chunk(FIRST_ID + 1, "train.py", (0.0, 1.0, 0.0)),
    chunk(FIRST_ID + 2, "model.py", (-1.0, 0.0, 0.0)),
]


def test_the_headers_come_back_in_chunk_order_without_their_text(db):
    write_artifact(db, artifact(), list(reversed(CHUNKS)))

    headers = read_headers(db, "m1")

    assert [h.chunk_index for h in headers] == [c.chunk_index for c in CHUNKS]
    assert [h.header for h in headers] == [c.header for c in CHUNKS]
    assert [(h.source, h.start_line, h.end_line) for h in headers] == [
        (c.source, c.start_line, c.end_line) for c in CHUNKS
    ]
    assert not hasattr(headers[0], "text"), "the map must never carry chunk text"


def test_a_map_of_an_artifact_never_stored_is_refused(db):
    with pytest.raises(UnknownArtifact):
        read_headers(db, "never-stored")


def test_a_file_scores_by_its_best_chunk_not_its_average(db):
    # a big file whose ONE function answers must still rank high
    write_artifact(db, artifact(), CHUNKS)

    scores = file_scores(db, "m1", QUERY, model=MODEL)

    assert scores["train.py"] == pytest.approx(1.0, abs=1e-6)
    assert scores["model.py"] == pytest.approx(-1.0, abs=1e-6)


def test_only_the_named_artifacts_files_are_scored(db):
    write_artifact(db, artifact(), CHUNKS)
    write_artifact(
        db,
        artifact(id="m2", side="A"),
        [chunk(FIRST_ID + 50, "paper.md", (1.0, 0.0, 0.0))],
    )

    assert set(file_scores(db, "m1", QUERY, model=MODEL)) == {"train.py", "model.py"}


def test_a_query_from_another_embedder_is_refused(db):
    write_artifact(db, artifact(), CHUNKS)
    with pytest.raises(ModelMismatch):
        file_scores(db, "m1", QUERY, model="gemini-embedding-001")


def test_scoring_an_artifact_never_stored_is_refused(db):
    with pytest.raises(UnknownArtifact):
        file_scores(db, "never-stored", QUERY, model=MODEL)


# ---- the opening: a few characters of the text, for the map's hints --------


def test_without_a_request_no_text_leaves_the_database(db):
    write_artifact(db, artifact(), CHUNKS)

    assert {h.opening for h in read_headers(db, "m1")} == {""}


def test_the_opening_is_the_first_characters_of_the_text_and_no_more(db):
    write_artifact(db, artifact(), CHUNKS)

    headers = read_headers(db, "m1", opening_chars=12)

    assert [h.opening for h in headers] == [c.text[:12] for c in CHUNKS]
    assert {len(h.opening) for h in headers} == {12}


SPLIT = [
    chunk(FIRST_ID, "t.py", (1.0, 0.0, 0.0), "[t.py · def a · part 1/12 · lines 1-6]"),
    chunk(
        FIRST_ID + 1, "t.py", (1.0, 0.0, 0.0), "[t.py · def a · part 2/12 · lines 5-9]"
    ),
    chunk(
        FIRST_ID + 2, "t.py", (1.0, 0.0, 0.0), "[t.py · def a · part 9/12 · lines 5-9]"
    ),
    chunk(
        FIRST_ID + 3, "t.py", (1.0, 0.0, 0.0), "[t.py · def a · part 10/12 · lines 5-9]"
    ),
    chunk(FIRST_ID + 4, "t.py", (1.0, 0.0, 0.0), "[t.py · def b · lines 20-25]"),
]


def test_only_a_chunk_that_starts_its_unit_brings_an_opening(db):
    # a later piece of a split function starts in the middle of its body, so
    # there is no signature in it to find, and sending its text is waste
    write_artifact(db, artifact(), SPLIT)

    openings = [h.opening != "" for h in read_headers(db, "m1", opening_chars=12)]

    assert openings == [True, False, False, False, True]


def test_a_folder_called_part_2_does_not_hide_the_openings_of_its_files(db):
    # the header starts with the source path, so "part 2/" is in it
    headers = [
        chunk(
            FIRST_ID,
            "part 2/main.py",
            (1.0, 0.0, 0.0),
            "[part 2/main.py · def f · lines 1-6]",
        )
    ]
    write_artifact(db, artifact(), headers)

    assert read_headers(db, "m1", opening_chars=12)[0].opening != ""


def test_a_negative_opening_is_a_caller_bug(db):
    with pytest.raises(ValueError, match="opening_chars"):
        read_headers(db, "m1", opening_chars=-1)
