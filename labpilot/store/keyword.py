from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import psycopg

from labpilot.store.contracts import SearchHit
from labpilot.store.defaults import BM25_B, BM25_K1, SEARCH_LIMIT
from labpilot.store.errors import UnknownArtifact

# Turning the query into an OR of its lexemes is the whole ballgame.
# plainto_tsquery joins with AND, and one 500-token chunk almost never holds
# every word of a sentence: measured 2026-09-06, AND scored recall@5 of 0.000
# on all 17 quora queries while OR scored 0.824.
#
# Two differences from the benchmark's version of this expression, both found
# by probing real input on 2026-09-07 and both silent failures:
#
#   quote_literal  -- a lexeme may contain ':', and to_tsquery reads that as a
#                     weight marker. "api.github.com:443" CRASHED with
#                     SyntaxError. Quoting also stops '&' inside a URL token
#                     from injecting an AND back into the query.
#   'simple'       -- these lexemes are ALREADY stemmed by to_tsvector, and
#                     re-stemming can change them: 'pleas' -> 'plea', which
#                     then no longer matches the stored 'pleas'. 'simple' does
#                     not stem, so a lexeme survives the round trip unchanged.
#
# The stored side stays 'english', because that is what the column holds.
_TSQUERY = """
    to_tsquery('simple', array_to_string(array(
        select quote_literal(lexeme)
        from unnest(tsvector_to_array(to_tsvector('english', %s))) as lexeme
    ), ' | '))
"""

_ARTIFACT = "select created_at from artifacts where id = %s"

# ts_rank, never ts_rank_cd: cover density lost on every run of the sweep.
_KEYWORD = f"""
    select c.chunk_index, c.text, c.header, c.source, c.start_line, c.end_line,
           ts_rank(c.tsv, q)::float8 as score
    from chunks c, {_TSQUERY} as q
    where c.artifact_id = %s and c.tsv @@ q
    order by score desc, c.chunk_index
    limit %s
"""

# N and L for one artifact. Cached, because an artifact is rewritten whole or
# not at all -- see _corpus for why the cache cannot go stale.
_CORPUS = """
    select count(*), coalesce(avg(d.len), 0)::float8
    from chunks c
    cross join lateral (
        select coalesce(sum(coalesce(array_length(t.positions, 1), 1)), 0) as len
        from unnest(c.tsv) t
    ) d
    where c.artifact_id = %s
"""

_TERMS = "select tsvector_to_array(to_tsvector('english', %s))"

# One row per MATCHING chunk, never one per lexeme: a common word can match
# most of the corpus, and returning every lexeme of every match would be
# hundreds of thousands of rows on a real artifact. `length` is the whole
# chunk, because BM25 normalises by document length; `terms`/`counts` are
# f(t,d), filtered to the query's terms.
_MATCHES = f"""
    select c.chunk_index,
           sum(t.cnt)::float8 as length,
           coalesce(
               array_agg(t.lexeme) filter (where t.lexeme = any(%s)),
               '{{}}'::text[]) as terms,
           coalesce(
               array_agg(t.cnt) filter (where t.lexeme = any(%s)),
               '{{}}'::int[]) as counts
    from chunks c
    cross join lateral (
        select lexeme, coalesce(array_length(positions, 1), 1) as cnt
        from unnest(c.tsv)
    ) t
    where c.artifact_id = %s and c.tsv @@ {_TSQUERY}
    group by c.chunk_index
"""

# n_t, the document frequency IDF needs. One indexed `@@` per term, but all of
# them in ONE round trip -- a ten-word query over a VPN would otherwise cost
# ten. The left join keeps a term that matches nothing, so it scores 0 rather
# than disappearing.
_DOCFREQ = """
    select t.lexeme, count(c.chunk_index)
    from unnest(%s::text[]) as t(lexeme)
    left join chunks c
        on c.artifact_id = %s
       and c.tsv @@ to_tsquery('simple', quote_literal(t.lexeme))
    group by t.lexeme
"""

_HITS = """
    select chunk_index, text, header, source, start_line, end_line
    from chunks
    where artifact_id = %s and chunk_index = any(%s)
"""


@dataclass(frozen=True, slots=True)
class _Corpus:
    n: int
    average_length: float


_CORPUS_CACHE: dict[tuple[str, datetime], _Corpus] = {}


def keyword_search(
    conn: psycopg.Connection,
    artifact_id: str,
    query: str,
    *,
    limit: int = SEARCH_LIMIT,
) -> tuple[SearchHit, ...]:
    _guard(conn, artifact_id, query, limit)

    with conn.cursor() as cur:
        cur.execute(_KEYWORD, (query, artifact_id, limit))
        rows = cur.fetchall()

    return tuple(
        SearchHit(
            chunk_index=chunk_index,
            text=text,
            header=header,
            source=source,
            start_line=start_line,
            end_line=end_line,
            score=score,
        )
        for chunk_index, text, header, source, start_line, end_line, score in rows
    )


def bm25_search(
    conn: psycopg.Connection,
    artifact_id: str,
    query: str,
    *,
    limit: int = SEARCH_LIMIT,
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> tuple[SearchHit, ...]:
    created_at = _guard(conn, artifact_id, query, limit)

    with conn.cursor() as cur:
        cur.execute(_TERMS, (query,))
        terms = list(cur.fetchone()[0] or ())
        if not terms:
            return ()

        corpus = _corpus(cur, artifact_id, created_at)
        if not corpus.n or not corpus.average_length:
            return ()

        cur.execute(_MATCHES, (terms, terms, artifact_id, query))
        matches = cur.fetchall()
        if not matches:
            return ()

        cur.execute(_DOCFREQ, (terms, artifact_id))
        document_frequency = dict(cur.fetchall())

        ranked = _rank(matches, document_frequency, corpus, k1=k1, b=b)[:limit]
        cur.execute(_HITS, (artifact_id, [index for index, _ in ranked]))
        rows = {row[0]: row for row in cur.fetchall()}

    return tuple(
        SearchHit(
            chunk_index=rows[index][0],
            text=rows[index][1],
            header=rows[index][2],
            source=rows[index][3],
            start_line=rows[index][4],
            end_line=rows[index][5],
            score=score,
        )
        for index, score in ranked
        if index in rows
    )


def _guard(
    conn: psycopg.Connection, artifact_id: str, query: str, limit: int
) -> datetime:
    """The same refusals as vector search, minus one that cannot apply.

    There is deliberately NO ModelMismatch check: words are compared with
    words, so there is no embedding space to get wrong.
    """
    if limit < 1:
        raise ValueError(f"limit must be positive, got {limit}")
    if not query.strip():
        raise ValueError("the query is empty")

    with conn.cursor() as cur:
        cur.execute(_ARTIFACT, (artifact_id,))
        row = cur.fetchone()

    if row is None:
        raise UnknownArtifact(
            f"no artifact {artifact_id!r} is stored: searching it would "
            f"return an empty result, which reads as 'nothing matched'"
        )
    return row[0]


def _corpus(cur: psycopg.Cursor, artifact_id: str, created_at: datetime) -> _Corpus:
    """N and the average chunk length, computed once per stored artifact.

    The key carries created_at, not the id alone. write_artifact replaces an
    artifact by deleting the row and inserting a new one, so a re-ingest gets a
    fresh timestamp and therefore a fresh cache entry. Keyed on the id alone,
    a rewritten artifact would keep scoring against the old corpus.
    """
    key = (artifact_id, created_at)
    cached = _CORPUS_CACHE.get(key)
    if cached is None:
        cur.execute(_CORPUS, (artifact_id,))
        n, average_length = cur.fetchone()
        cached = _Corpus(n=n, average_length=float(average_length))
        _CORPUS_CACHE[key] = cached
    return cached


def _rank(
    matches: list[tuple[int, float, list[str], list[int]]],
    document_frequency: dict[str, int],
    corpus: _Corpus,
    *,
    k1: float,
    b: float,
) -> list[tuple[int, float]]:
    """BM25, which Postgres cannot do.

    ts_rank(tsvector, tsquery) is handed ONE document, so it cannot know how
    many documents hold a term and has no IDF at all. That is the whole
    difference: without IDF a common word counts as much as a rare one, and an
    OR query over common words matches nearly everything.
    """
    scored: list[tuple[int, float]] = []

    for chunk_index, length, terms, counts in matches:
        total = 0.0
        for term, frequency in zip(terms, counts, strict=True):
            n_t = document_frequency.get(term, 0)
            if not n_t or not frequency:
                continue
            idf = math.log((corpus.n - n_t + 0.5) / (n_t + 0.5) + 1.0)
            norm = k1 * (1 - b + b * length / corpus.average_length)
            total += idf * (frequency * (k1 + 1)) / (frequency + norm)
        if total > 0:
            scored.append((chunk_index, total))

    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored
