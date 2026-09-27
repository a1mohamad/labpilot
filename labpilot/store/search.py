from __future__ import annotations

import psycopg

from labpilot.store.contracts import SearchHit, Vector
from labpilot.store.defaults import SEARCH_LIMIT
from labpilot.store.errors import ModelMismatch, UnknownArtifact

_ARTIFACT = "select embedding_model, dim from artifacts where id = %s"

# Exact search: no index exists, so every row of the artifact is compared.
# That is the point - exact is correct BY DEFINITION, which makes it the only
# instrument that can score an approximate index later.
#
# `<=>` is cosine DISTANCE, not similarity: smallest is nearest, so there is
# no `desc` here. `score` flips it back to similarity for the reader, and is
# deliberately NOT what we sort on - wrapping the distance in `1 - (...)`
# stops pgvector recognising the shape, and an HNSW index would silently be
# skipped for a full scan. Measured 2026-08-28: 5x slower at only 2,000 rows,
# with no error and no warning.
#
# `::vector` is NOT load-bearing, measured 2026-09-05: removing both casts
# changed nothing, because psycopg3 sends the parameter as `unknown` and
# Postgres coerces it to match the operator. It is kept as belt-and-braces -
# a driver that ever typed the parameter as `text` would make
# `vector <=> text` fail to resolve - but no test pins it, and none should
# pretend to.
_SEARCH = """
    select chunk_index, text, header, source, start_line, end_line,
           1 - (v <=> %s::vector) as score
    from chunks
    where artifact_id = %s
    order by v <=> %s::vector
    limit %s
"""


# How close each FILE comes to the question: the score of its BEST chunk.
#
# MAX, not the mean. A file is worth showing if ANY part of it answers - a
# 900-line trainer whose one clipping line is the answer would average out to
# nothing, the same dilution that makes a large chunk retrieve badly. One pass
# over the artifact's rows, exact, like _SEARCH; nothing but a number per file
# crosses the wire.
_FILE_SCORES = """
    select source, max(1 - (v <=> %s::vector))
    from chunks
    where artifact_id = %s
    group by source
"""


def search(
    conn: psycopg.Connection,
    artifact_id: str,
    query: Vector,
    *,
    model: str,
    limit: int = SEARCH_LIMIT,
) -> tuple[SearchHit, ...]:
    if limit < 1:
        raise ValueError(f"limit must be positive, got {limit}")

    with conn.cursor() as cur:
        vector = _checked(cur, artifact_id, query, model=model)
        cur.execute(_SEARCH, (vector, artifact_id, vector, limit))
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


def file_scores(
    conn: psycopg.Connection,
    artifact_id: str,
    query: Vector,
    *,
    model: str,
) -> dict[str, float]:
    with conn.cursor() as cur:
        vector = _checked(cur, artifact_id, query, model=model)
        cur.execute(_FILE_SCORES, (vector, artifact_id))
        rows = cur.fetchall()

    return {source: float(score) for source, score in rows}


def _checked(cur, artifact_id: str, query: Vector, *, model: str) -> str:
    """Refuse a query that cannot be compared with this artifact's vectors.

    Shared by every read that takes a query vector, because each failure here
    is SILENT otherwise: a missing artifact returns nothing, and a vector from
    another model returns numbers that look fine and mean nothing.
    """
    if not query:
        raise ValueError("the query vector is empty")

    cur.execute(_ARTIFACT, (artifact_id,))
    row = cur.fetchone()
    if row is None:
        raise UnknownArtifact(
            f"no artifact {artifact_id!r} is stored: searching it would "
            f"return an empty result, which reads as 'nothing matched'"
        )

    stored_model, dim = row
    if stored_model != model:
        raise ModelMismatch(
            f"artifact {artifact_id!r} was embedded with {stored_model!r} "
            f"but this query was embedded with {model!r}: two embedding "
            f"spaces do not compare, and the numbers would look fine"
        )
    if len(query) != dim:
        raise ValueError(
            f"the query has {len(query)} dimensions, but artifact "
            f"{artifact_id!r} stores {dim}"
        )

    return str(list(query))
