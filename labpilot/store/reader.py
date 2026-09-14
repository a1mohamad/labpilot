from __future__ import annotations

import psycopg

from labpilot.store.contracts import ArtifactRecord, StoredArtifact, StoredChunk
from labpilot.store.errors import UnknownArtifact

# `embed_text` is `header + "\n" + text`, and the newline exists ONLY when the
# header does - Chunk.embed_text returns bare text otherwise. CLAUDE.md's
# sketch of this query wrote a flat `+ 1`, which over-counts by one character
# for every header-less chunk. Every chunk the chunker builds carries a header
# today, so the flat version would have been right by luck and wrong by rule,
# and no test or error would ever have said so.
_LENGTH = (
    "length(c.header) + length(c.text) + case when c.header = '' then 0 else 1 end"
)

# One round trip, and not one chunk row crosses the wire.
#
# The LEFT JOIN separates "not stored" from "stored and empty": a missing id
# yields no row at all, while a stored artifact with no chunks yields a single
# row of zeroes.
#
# It is NOT load-bearing today, and a mutation proved it: swapping LEFT for an
# INNER join leaves all six tests green. write_artifact REFUSES an artifact
# with zero chunks, so "stored and empty" cannot be reached through any write
# path we have. The LEFT JOIN is kept because it is free and it is the honest
# shape - but no test pins it, and none should pretend to, exactly as with the
# ::vector cast in search.py.
#
# `group by a.id` alone is legal because id is the PRIMARY KEY, so Postgres
# knows every other artifacts column is functionally dependent on it.
_MEASURE = f"""
    select a.name, a.side, a.embedding_model, a.dim,
        count(c.chunk_index), coalesce(sum({_LENGTH}), 0)
    from artifacts a
    left join chunks c on c.artifact_id = a.id
    where a.id = %s
    group by a.id
"""

# ORDER BY is CORRECTNESS here, not tidiness, and it is the same lesson slice 2
# learned about sorting a repository walk. Prompt ids are POSITIONAL -
# assign_ids walks the tuple and hands out A-0, A-1, A-2 - so a different row
# order renames every chunk, and a citation then points at the wrong file with
# full confidence. Postgres promises no order at all without this line.
_CHUNKS = """
    select chunk_index, text, header, source, start_line, end_line
    from chunks
    where artifact_id = %s
    order by chunk_index
"""

_EXIST = "select 1 from artifacts where id = %s"


def measure(conn: psycopg.Connection, artifact_id: str) -> StoredArtifact:
    with conn.cursor() as cur:
        cur.execute(_MEASURE, (artifact_id,))
        row = cur.fetchone()

    if row is None:
        raise UnknownArtifact(
            f"no artifact {artifact_id!r} is stored: reporting it as empty "
            f"would read as 'this file holds nothing', which is a lie about "
            f"whose fault it is"
        )

    name, side, model, dim, chunks, characters = row
    return StoredArtifact(
        artifact=ArtifactRecord(
            id=artifact_id,
            name=name,
            side=side,
            embedding_model=model,
            dim=dim,
        ),
        chunks=chunks,
        characters=characters,
    )


def read_chunks(conn: psycopg.Connection, artifact_id: str) -> tuple[StoredChunk, ...]:
    with conn.cursor() as cur:
        cur.execute(_CHUNKS, (artifact_id,))
        rows = cur.fetchall()

        if not rows:
            cur.execute(_EXIST, (artifact_id,))
            if cur.fetchone() is None:
                raise UnknownArtifact(
                    f"no artifact {artifact_id!r} is stored: returning no "
                    f"chunks would read as 'there is nothing to compare'"
                )

    return tuple(
        StoredChunk(
            chunk_index=chunk_index,
            text=text,
            header=header,
            source=source,
            start_line=start_line,
            end_line=end_line,
        )
        for chunk_index, text, header, source, start_line, end_line in rows
    )
