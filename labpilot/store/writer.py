from __future__ import annotations

from collections.abc import Iterable
from itertools import batched

import psycopg

from labpilot.store.contracts import ArtifactRecord, ChunkRecord
from labpilot.store.defaults import INSERT_BATCH_SIZE

_INSERT_ARTIFACT = """
    insert into artifacts (id, name, side, embedding_model, dim)
    values (%s, %s, %s, %s, %s)
"""

_INSERT_CHUNK = """
    insert into chunks
        (artifact_id, chunk_index, text, header, source,
        start_line, end_line, v)
    values (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def write_artifact(
    conn: psycopg.Connection,
    artifact: ArtifactRecord,
    chunks: Iterable[ChunkRecord],
) -> int:
    written = 0

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("delete from artifacts where id = %s", (artifact.id,))
        cur.execute(
            _INSERT_ARTIFACT,
            (
                artifact.id,
                artifact.name,
                artifact.side,
                artifact.embedding_model,
                artifact.dim,
            ),
        )

        for batch in batched(chunks, INSERT_BATCH_SIZE):
            cur.executemany(_INSERT_CHUNK, [_row(artifact, c) for c in batch])
            written += len(batch)

        if written == 0:
            raise ValueError(
                f"artifact {artifact.id!r} has no chunks: storing it would "
                f"give a corpus that returns empty results and says nothing"
            )

    return written


def _row(artifact: ArtifactRecord, chunk: ChunkRecord) -> tuple[object, ...]:
    if len(chunk.vector) != artifact.dim:
        raise ValueError(
            f"chunk {chunk.chunk_index} of artifact {artifact.id!r} has "
            f"{len(chunk.vector)} dimensions, but the artifact declares "
            f"{artifact.dim}"
        )

    return (
        artifact.id,
        chunk.chunk_index,
        chunk.text,
        chunk.header,
        chunk.source,
        chunk.start_line,
        chunk.end_line,
        str(list(chunk.vector)),
    )
