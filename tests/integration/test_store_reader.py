from __future__ import annotations

import pytest

from labpilot.ingest import chunk_bytes
from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    UnknownArtifact,
    measure,
    read_chunks,
    write_artifact,
)

pytestmark = pytest.mark.database

MODEL = "codestral-embed"
DIM = 3
V = (1.0, 0.0, 0.0)

# Chunk ids start at 100, never 0. Slice 5 learned this the hard way: a fixture
# numbered from zero cannot tell a chunk_index from a row position, because
# both are valid small integers. Offset ids make the confusion provable.
FIRST_ID = 100


def artifact(**overrides) -> ArtifactRecord:
    fields = {
        "id": "r1",
        "name": "train.py",
        "side": "B",
        "embedding_model": MODEL,
        "dim": DIM,
    }
    return ArtifactRecord(**{**fields, **overrides})


def record(index: int, text: str, header: str) -> ChunkRecord:
    return ChunkRecord(
        chunk_index=index,
        text=text,
        header=header,
        source="train.py",
        start_line=index * 10,
        end_line=index * 10 + 5,
        vector=V,
    )


def test_the_characters_match_what_python_would_measure(db):
    """THE invariant of this module, and the reason the SQL is worth trusting.

    store/ may not import ingest/, so the database computes the length of
    `embed_text` from its own two columns and nothing proves the two agree.
    A test may import both, so it can hold the rule the packages cannot.

    Real chunks from the real chunker, not hand-written rows - the question is
    whether the SQL reproduces what ingest actually measured.
    """
    source = b"def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
    chunks = chunk_bytes(source, source="train.py", side="B", artifact_id="r1")
    assert chunks, "the fixture must produce chunks or this test proves nothing"

    write_artifact(
        db,
        artifact(),
        [
            ChunkRecord(
                chunk_index=c.chunk_index,
                text=c.text,
                header=c.header,
                source=c.source,
                start_line=c.start_line,
                end_line=c.end_line,
                vector=V,
            )
            for c in chunks
        ],
    )

    size = measure(db, "r1")

    assert size.chunks == len(chunks)
    assert size.characters == sum(len(c.embed_text) for c in chunks)


def test_a_chunk_with_no_header_is_counted_without_a_newline(db):
    """`embed_text` joins header and text with a newline ONLY when there is a
    header - Chunk.embed_text returns bare text otherwise.

    CLAUDE.md's sketch of this query wrote a flat `+ 1`. Every chunk the
    chunker builds carries a header, so that version would have been right by
    luck on every real corpus and wrong by rule, with nothing to report it.

        no header   len("hello") .................. 5
        a header    len("[h]") + 1 + len("de") .... 6
        total ....................................  11

    A flat `+ 1` gives 12. `length()` counting BYTES instead of characters also
    gives 12, because the text below is deliberately non-ASCII - so this one
    assertion pins both.
    """
    write_artifact(
        db,
        artifact(),
        [record(FIRST_ID, "héllo", ""), record(FIRST_ID + 1, "de", "[h]")],
    )

    assert measure(db, "r1").characters == 11


def test_measure_reports_the_model_the_artifact_was_embedded_with(db):
    """The ask path cannot embed its question without this.

    A query vector must come from the SAME model the corpus was stored with -
    search() refuses a mismatch - so the caller has to learn the model from
    somewhere, and one round trip that already reads the artifacts row is the
    cheapest place to get it.
    """
    write_artifact(
        db, artifact(embedding_model="mistral-embed"), [record(FIRST_ID, "x", "[h]")]
    )

    assert measure(db, "r1").artifact.embedding_model == "mistral-embed"


def test_measuring_an_unknown_artifact_is_refused(db):
    """count(*) over nothing is 0, and 0 reads as "this file holds no text".

    That is a lie about whose fault it is, and it is the same refusal search()
    already makes for the same reason.
    """
    with pytest.raises(UnknownArtifact, match="nope"):
        measure(db, "nope")


def test_every_chunk_comes_back_in_chunk_index_order(db):
    """Prompt ids are POSITIONAL - assign_ids hands out A-0, A-1, A-2 by
    walking the tuple - so row order decides which chunk each citation names.
    Postgres promises no order without ORDER BY, so the rows go in scrambled.

    The header and line numbers are asserted too: they are what turns a hit
    back into `train.py:1203`, and a read path that dropped them would still
    look fine to a test that only counted rows.
    """
    write_artifact(
        db,
        artifact(),
        [
            record(FIRST_ID + 2, "third", "[c]"),
            record(FIRST_ID, "first", "[a]"),
            record(FIRST_ID + 1, "second", "[b]"),
        ],
    )

    chunks = read_chunks(db, "r1")

    assert [c.chunk_index for c in chunks] == [FIRST_ID, FIRST_ID + 1, FIRST_ID + 2]
    assert [c.text for c in chunks] == ["first", "second", "third"]
    assert chunks[0].header == "[a]"
    assert (chunks[0].start_line, chunks[0].end_line) == (
        FIRST_ID * 10,
        FIRST_ID * 10 + 5,
    )


def test_reading_an_unknown_artifact_is_refused(db):
    """An empty tuple reads as "there is nothing to compare", which is the same
    silent failure measure() refuses - so both doors answer the same way.

    Only the EMPTY answer is ambiguous, so only it pays for a second query.
    That second query must run INSIDE the cursor's `with`, or it raises
    InterfaceError instead - the mistake write_artifact made first, where four
    spaces of indentation decided whether the write was atomic.
    """
    with pytest.raises(UnknownArtifact, match="nope"):
        read_chunks(db, "nope")
