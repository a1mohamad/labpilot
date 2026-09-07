from __future__ import annotations

import pytest

from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    UnknownArtifact,
    bm25_search,
    keyword_search,
    write_artifact,
)

pytestmark = pytest.mark.database

# Both doors, wherever the invariant belongs to the query and not to the
# ranking. They share _TSQUERY, so a break there must show up on both.
BOTH = pytest.mark.parametrize(
    "search_fn", [keyword_search, bm25_search], ids=["ts_rank", "bm25"]
)

# Made-up words on purpose: none of them is an English stopword, and none
# stems into another, so the only thing that moves a score is the rule under
# test. "filler" pads a chunk to a chosen length without being searched for.
FILLERS = (
    "bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike "
    "november oscar papa quebec sierra tango uniform victor"
).split()


def stored(
    db,
    artifact_id: str,
    bodies,
    *,
    headers=None,
    dim: int = 3,
    first=0,
    vectors=None,
):
    """Write one artifact whose chunks are (header, text) pairs.

    `first` shifts the chunk indexes. Two artifacts numbered from 0 would
    collide, and a leak from one into the other could then be hidden by the
    second artifact happening to hold the same index.
    """
    record = ArtifactRecord(
        id=artifact_id, name="train.py", side="B", embedding_model="m", dim=dim
    )
    chunks = [
        ChunkRecord(
            chunk_index=first + offset,
            text=text,
            header=(headers[offset] if headers else ""),
            source="train.py",
            start_line=offset * 10,
            end_line=offset * 10 + 5,
            vector=(vectors[offset] if vectors else tuple([1.0] + [0.0] * (dim - 1))),
        )
        for offset, text in enumerate(bodies)
    ]
    write_artifact(db, record, chunks)
    return record


def scores(hits):
    return {hit.chunk_index: hit.score for hit in hits}


def test_a_chunk_matches_on_a_word_from_its_header(db):
    """The tsvector reads `header || ' ' || text`, never text alone.

    The benchmark scored `embed_text`, which is header plus text. A tsvector
    over text alone would lose every file and function name - exactly the
    words a question about code uses - and the measured numbers would not
    transfer.
    """
    stored(
        db,
        "hdr",
        ["returns the running value"],
        headers=["[train.py - def clip_gradients - lines 1-9]"],
    )

    hits = bm25_search(db, "hdr", "how are gradients clipped")

    assert [hit.chunk_index for hit in hits] == [0]


@BOTH
def test_the_query_words_are_joined_with_or_so_a_partial_match_counts(db, search_fn):
    """AND scored recall@5 of 0.000 on all 17 quora queries; OR scored 0.824.

    No chunk of 500 tokens holds every word of a sentence, so joining the
    query's words with AND matches almost nothing. This is the single most
    expensive thing the keyword path can get wrong.
    """
    stored(db, "orq", ["alpha nothing else", "bravo nothing else"])

    hits = search_fn(db, "orq", "alpha bravo charlie")

    assert {hit.chunk_index for hit in hits} == {0, 1}


def test_a_rare_word_outranks_a_common_one(db):
    """IDF, and it is the ONLY thing separating BM25 from ts_rank.

    ts_rank(tsvector, tsquery) is handed one document, so it cannot know how
    many documents hold a term. Without IDF both chunks below score the same
    and the tie falls to the lower chunk_index, which is chunk 0.
    """
    bodies = ["commonword filler"] * 9 + ["rareword filler"]
    stored(db, "idf", bodies)

    hits = bm25_search(db, "idf", "commonword rareword")

    assert hits[0].chunk_index == 9


def test_ten_occurrences_do_not_score_ten_times_one(db):
    """Saturation, the k1 term. Both chunks are the same LENGTH on purpose,
    so length normalisation cannot be what produces the difference."""
    stored(db, "sat", ["alpha " * 10, " ".join(["alpha", *FILLERS[:9]])])

    got = scores(bm25_search(db, "sat", "alpha"))

    assert got[0] > got[1]
    assert got[0] < 5 * got[1]


def test_a_longer_chunk_scores_lower_at_the_same_word_count(db):
    """Length normalisation, the b term. Both chunks hold `alpha` exactly
    once; only their length differs. The long chunk is chunk 0, so if the
    rule is removed the tie falls to it and this test fails."""
    stored(
        db,
        "len",
        [" ".join(["alpha", *FILLERS[:19]]), " ".join(["alpha", *FILLERS[:4]])],
    )

    hits = bm25_search(db, "len", "alpha")

    assert hits[0].chunk_index == 1


@BOTH
def test_a_query_holding_an_operator_lexeme_does_not_crash(db, search_fn):
    """Found by probing real input 2026-09-07, and it was a CRASH.

    A lexeme may contain ':' - "api.github.com:443" is one token - and
    to_tsquery reads ':' as a weight marker, raising SyntaxError. quote_literal
    is what stops it, and it also stops '&' inside a URL token from injecting
    an AND back into an OR query.
    """
    stored(db, "ops", ["connecting to a host and a port"])

    hits = search_fn(db, "ops", "connect to api.github.com:443 now")

    assert isinstance(hits, tuple)


@BOTH
def test_a_word_whose_stem_would_drift_still_matches(db, search_fn):
    """The query is built with 'simple', never 'english', and this is why.

    to_tsvector('english', ...) already stemmed these words. Stemming them a
    SECOND time can change them - measured, 'pleas' becomes 'plea' - and the
    changed lexeme then no longer matches what is stored. 'simple' does not
    stem, so a lexeme survives the round trip unchanged.
    """
    stored(db, "stem", ["please read the configuration"])

    hits = search_fn(db, "stem", "please")

    assert [hit.chunk_index for hit in hits] == [0]


@BOTH
def test_only_the_named_artifact_is_searched(db, search_fn):
    """bm25 filters by artifact TWICE - once when it gathers the term counts,
    and again when it fetches the rows to return.

    The second filter alone would still hand back only our own rows, so a
    broken first filter looks harmless. It is not: foreign chunks would be
    scored, ranked, and would push real answers out of the limit. The other
    artifact therefore scores HIGHER here and its indexes do not collide with
    ours, so a leak costs us hits instead of hiding behind them.
    """
    stored(db, "mine", ["alpha one", "alpha two"])
    stored(db, "other", ["alpha alpha alpha"] * 5, first=10)

    hits = search_fn(db, "mine", "alpha", limit=2)

    assert {hit.chunk_index for hit in hits} == {0, 1}


@BOTH
def test_an_unknown_artifact_is_refused_rather_than_returning_nothing(db, search_fn):
    """Empty and absent are different facts. Returning () for an artifact that
    was never stored reads as "nothing matched", and the corpus is missing."""
    with pytest.raises(UnknownArtifact, match="nope"):
        search_fn(db, "nope", "alpha")


@BOTH
@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"limit": 0}, "limit"), ({"limit": -1}, "limit")],
    ids=["limit-zero", "limit-negative"],
)
def test_a_limit_that_returns_nothing_is_a_caller_bug(db, search_fn, kwargs, message):
    # Store it first, so the limit guard is the ONLY thing that can refuse.
    stored(db, "lim", ["alpha"])

    with pytest.raises(ValueError, match=message):
        search_fn(db, "lim", "alpha", **kwargs)


@BOTH
def test_a_blank_query_is_a_caller_bug(db, search_fn):
    stored(db, "blank", ["alpha"])

    with pytest.raises(ValueError, match="empty"):
        search_fn(db, "blank", "   ")


def test_a_query_of_only_stopwords_returns_nothing_rather_than_everything(db):
    """ "the and of is" has no lexemes at all. That is a useless question, not
    a broken one, so it answers with nothing instead of raising."""
    stored(db, "stop", ["alpha bravo"])

    assert bm25_search(db, "stop", "the and of is") == ()


def test_a_hit_carries_the_line_numbers_a_citation_needs(db):
    """bm25_search reads _HITS BY POSITION, so a column reordered in the SQL
    would silently put the header in `source` and the wrong number on a
    citation."""
    stored(db, "cite", ["alpha bravo"], headers=["[train.py - def go]"])

    best = bm25_search(db, "cite", "alpha")[0]

    assert (best.text, best.source) == ("alpha bravo", "train.py")
    assert (best.start_line, best.end_line) == (0, 5)
    assert best.header == "[train.py - def go]"


def test_a_rewritten_artifact_is_not_scored_against_the_old_corpus(db):
    """N and L are cached, and the key carries created_at for this reason.

    Keyed on the artifact id alone, an artifact that is re-ingested keeps
    scoring against the corpus it USED to have - silently, because every
    number still looks reasonable. The control is the same content under an
    id that was never cached, so the two must agree exactly.
    """
    small = ["alpha filler", "beta filler"]
    large = ["alpha filler"] + [" ".join(FILLERS)] * 9

    stored(db, "reused", small)
    bm25_search(db, "reused", "alpha")  # fills the cache with the SMALL corpus

    stored(db, "reused", large)
    stored(db, "control", large)

    assert scores(bm25_search(db, "reused", "alpha")) == scores(
        bm25_search(db, "control", "alpha")
    )


def test_the_two_channels_rank_the_same_id_space_and_fuse(db):
    """The seam slice 7 will wire, tested before anything depends on it.

    Vector search and BM25 are different queries over different columns, and
    fusion only means anything if the numbers they return are the SAME
    identifiers. Nothing else in the suite checks that: each channel is tested
    alone, and `weighted_rrf` is pure arithmetic that never sees a database.

    The chunk indexes start at 100 on purpose. A layer that ever returned a
    row POSITION instead of a chunk_index would hand back 0..3 here, and every
    downstream citation would point at the wrong lines while still resolving.
    """
    from labpilot.retrieval import weighted_rrf
    from labpilot.store import search

    # Deliberate geometry, so the vector order is arithmetic and not a guess:
    # 100 points straight at the query, 101 is a small turn away, 102 is at a
    # right angle. `alpha` is in 100 and 101 only, so 100 leads BOTH channels.
    places = {100: (1.0, 0.0, 0.0), 101: (0.9, 0.436, 0.0), 102: (0.0, 1.0, 0.0)}
    stored(
        db,
        "seam",
        ["alpha beta", "alpha gamma", "delta epsilon"],
        first=100,
        vectors=list(places.values()),
    )

    dense = [hit.chunk_index for hit in search(db, "seam", (1.0, 0.0, 0.0), model="m")]
    sparse = [hit.chunk_index for hit in bm25_search(db, "seam", "alpha")]
    fused = weighted_rrf(dense, sparse)

    assert dense == list(places), "vector search must rank every chunk, nearest first"
    assert sparse == [100, 101], "only the two chunks holding `alpha` may match"
    assert set(fused) == set(places), "fusion must not invent or drop an id"
    assert fused[0] == 100, "the chunk both channels put first must come first"
