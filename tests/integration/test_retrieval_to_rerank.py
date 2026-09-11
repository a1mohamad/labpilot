"""The RAG path end to end: chunk -> store -> search -> rerank -> real chunks.

WHY THIS EXISTS
===============
Every layer is tested alone and the SEAM between the last two is not, and that
seam is the one place in this pipeline where a silent off-by-one cites the
wrong file with full confidence:

    store.search()  returns SearchHit.chunk_index  - an id in the corpus
    rerank()        returns POSITIONS into the list it was handed

Those two number spaces look identical and mean different things. `rerank/` is
an adapter and may not import `store/`, so nothing inside either package can
check the translation - it belongs to the caller, and slice 7 is about to write
it. CLAUDE.md's own warning for this shape:

    "The position is what the caller uses to look a chunk back up, so an index
     off by one cites the wrong file and line with full confidence."

The fixture is deliberately built so the two spaces CANNOT be confused: the
chunks are stored at ids 100+, so a position used as an id, or an id used as a
position, is out of range or points somewhere provably wrong. That is the same
correction slice 5 needed when a test numbered its chunks from zero and could
not tell an id from a row.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from labpilot.rerank import Ranking, rerank
from labpilot.store import ChunkRecord, search, write_artifact
from labpilot.store.contracts import ArtifactRecord

pytestmark = pytest.mark.database


@dataclass
class FakeReranker:
    """The Reranker protocol wants a .rank METHOD, so a bare function will not
    do - a mistake worth keeping in the fixture rather than hiding."""

    order: tuple[int, ...]
    model: str = "fake-rerank"

    def rank(self, query, documents, *, top_n=None):
        order = self.order if top_n is None else self.order[:top_n]
        return Ranking(order=order, model=self.model)


MODEL = "test-embed"
DIM = 3

# Chunk ids start at 100 on purpose - see the module docstring.
FIRST_ID = 100

# Three chunks placed by hand against the query [1, 0, 0]. The vector order is
# KNOWN and different from the rerank order, so a test that silently skipped
# reranking would still fail.
ROWS = (
    ("the optimizer is built here", (1.0, 0.0, 0.0)),  # nearest by vector
    ("gradients are clipped at 1.5", (0.9, 0.436, 0.0)),  # the real answer
    ("unrelated helper", (0.0, 1.0, 0.0)),  # furthest
)


def _stored(db, artifact_id: str) -> list[str]:
    write_artifact(
        db,
        ArtifactRecord(
            id=artifact_id, name="t.py", side="B", embedding_model=MODEL, dim=DIM
        ),
        (
            ChunkRecord(
                chunk_index=FIRST_ID + offset,
                text=text,
                source="t.py",
                start_line=offset * 10 + 1,
                end_line=offset * 10 + 9,
                vector=vector,
            )
            for offset, (text, vector) in enumerate(ROWS)
        ),
    )
    return [text for text, _ in ROWS]


def test_a_reranked_position_resolves_back_to_the_right_stored_chunk(db):
    """The translation slice 7 has to write, done once and checked.

    A reranker that promotes the second document must end up naming the chunk
    whose id is FIRST_ID + 1 - not chunk 1, and not row 1.
    """
    _stored(db, "seam")
    hits = search(db, "seam", (1.0, 0.0, 0.0), model=MODEL)

    assert [hit.chunk_index for hit in hits] == [FIRST_ID, FIRST_ID + 1, FIRST_ID + 2]

    # Puts the SECOND hit first, deliberately disagreeing with the vector
    # order so the test cannot pass by accident.
    promote_second = FakeReranker(order=(1, 0, 2))

    ranking = rerank("why", [hit.text for hit in hits], chain=(promote_second,))
    reordered = [hits[position] for position in ranking.order]

    assert [hit.chunk_index for hit in reordered] == [
        FIRST_ID + 1,
        FIRST_ID,
        FIRST_ID + 2,
    ]
    assert reordered[0].text == "gradients are clipped at 1.5"
    assert reordered[0].start_line == 11


def test_the_documents_sent_to_the_reranker_are_the_ones_that_were_stored(db):
    """A reranker judges the TEXT. If the caller sends anything other than what
    the store holds, every score is about a string nobody will ever cite."""
    texts = _stored(db, "sent")
    hits = search(db, "sent", (1.0, 0.0, 0.0), model=MODEL)

    assert sorted(hit.text for hit in hits) == sorted(texts)


def test_when_every_reranker_fails_the_retrieval_order_survives_intact(db):
    """The degraded path, through real search rather than a fixture.

    This is what the pipeline does whenever the gate skips or the chain is
    exhausted, so the chunk ids it produces must still be the search order.
    """
    _stored(db, "degraded")
    hits = search(db, "degraded", (1.0, 0.0, 0.0), model=MODEL)

    ranking = rerank("why", [hit.text for hit in hits], chain=())
    reordered = [hits[position] for position in ranking.order]

    assert ranking.skipped
    assert [hit.chunk_index for hit in reordered] == [hit.chunk_index for hit in hits]


def test_top_n_keeps_the_best_chunks_and_not_the_first_ones(db):
    """top_n cuts the RERANKED order. Cutting the search order instead would
    silently undo the reranking while still returning the right count."""
    _stored(db, "cut")
    hits = search(db, "cut", (1.0, 0.0, 0.0), model=MODEL)

    reverse = FakeReranker(order=(2, 1, 0), model="rev")

    ranking = rerank("why", [h.text for h in hits], chain=(reverse,), top_n=2)
    kept = [hits[position].chunk_index for position in ranking.order]

    assert kept == [FIRST_ID + 2, FIRST_ID + 1]


def test_a_hit_list_and_a_ranking_cannot_be_confused_by_length(db):
    """A guard on the fixture itself.

    Chunk ids start at 100, so a position used as an id is out of range and an
    id used as a position raises. Without that separation this whole file could
    pass while the translation was wrong - which is exactly how slice 5's
    search tests were unable to tell an id from a row number.
    """
    _stored(db, "distinct")
    hits = search(db, "distinct", (1.0, 0.0, 0.0), model=MODEL)

    ids = {hit.chunk_index for hit in hits}
    positions = set(range(len(hits)))

    assert not (ids & positions), "ids and positions must not overlap"


def test_a_position_that_was_never_sent_fails_LOUDLY_at_the_caller(db):
    """A correction to what this file first claimed.

    `Ranking` does NOT refuse an out-of-range position - it cannot, because it
    never learns how many documents were sent. The range check lives in
    HTTPReranker._validated, which does know, and LLMReranker clamps in its own
    parser. A hand-built ranking has neither.

    What actually protects the citation is that the caller indexes a list: an
    impossible position raises IndexError rather than quietly naming the wrong
    chunk. Loud is the property worth pinning; "impossible" was wishful.
    """
    _stored(db, "corrupt")
    hits = search(db, "corrupt", (1.0, 0.0, 0.0), model=MODEL)

    corrupt = Ranking(order=(0, len(hits) + 5), model="corrupt")

    with pytest.raises(IndexError):
        [hits[position] for position in corrupt.order]
