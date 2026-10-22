from __future__ import annotations

import math

import psycopg

from labpilot.api.errors import (
    ArtifactSidesClash,
    UnknownArtifactId,
)
from labpilot.ingest import (
    Chunk,
    Side,
)
from labpilot.prompts import (
    OUTLINE_BUDGET,
    PROMPT_BUDGET,
    instructions_for,
)
from labpilot.retrieval import LABEL_TOKENS
from labpilot.store import (
    SearchHit,
    StoredArtifact,
    StoredChunk,
    UnknownArtifact,
    measure,
    read_chunks,
)
from labpilot.tokens import CHARS_PER_TOKEN, estimate_tokens


def measure_sides(
    conn: psycopg.Connection, a_id: str, b_id: str
) -> dict[Side, StoredArtifact]:
    """Measure both artifacts, and take each one's side from the STORED row.

    Not from the request slot. `_artifact_id` is `f"{side}-{hash}"`, so the
    side is already baked into the id and the same file uploaded twice is two
    corpora - letting the slot disagree with the row would be two sources of
    truth for one fact.
    """
    found: dict[Side, StoredArtifact] = {}
    for artifact_id in (a_id, b_id):
        if not artifact_id:
            continue
        try:
            stored = measure(conn, artifact_id)
        except UnknownArtifact as exc:
            raise UnknownArtifactId(str(exc)) from exc

        if stored.artifact.side in found:
            raise ArtifactSidesClash(
                f"both {a_id!r} and {b_id!r} are side "
                f"{stored.artifact.side!r}: a comparison needs one of each"
            )
        found[stored.artifact.side] = stored

    return found


def fits_whole(sides: dict[Side, StoredArtifact], *, question: str) -> bool:
    """Would both artifacts fit the prompt whole, without reading a single row?

    Deliberately CONSERVATIVE, and it errs toward searching. The outline is
    charged at its full OUTLINE_BUDGET even though the ladder usually renders
    far less, because the real cost cannot be known without the headers - and
    the headers are the thing this check exists to avoid fetching.

    So a corpus near the line is searched when it could have been stuffed.
    That is the safe direction: searching still answers, while a wrong `yes`
    means reading ~14MB over the wire to discover it did not fit.
    """
    evidence = sum(
        math.ceil(found.characters / CHARS_PER_TOKEN) + found.chunks * LABEL_TOKENS
        for found in sides.values()
    )
    instructions = instructions_for(len(sides))
    fixed = estimate_tokens(f"{instructions.header}{instructions.closing}{question}")

    return evidence + fixed + OUTLINE_BUDGET <= PROMPT_BUDGET


def stuffed_chunks(
    conn: psycopg.Connection, sides: dict[Side, StoredArtifact]
) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    for side, found in sides.items():
        chunks.extend(
            as_chunk(stored, side, found.artifact.id)
            for stored in read_chunks(conn, found.artifact.id)
        )

    return tuple(chunks)


def as_chunk(stored: SearchHit | StoredChunk, side: Side, artifact_id: str) -> Chunk:
    """store/ -> ingest/, and entry is the only layer allowed to do it.

    Neither StoredChunk nor SearchHit carries `side` or `artifact_id`, because
    store/ is an adapter and may not import ingest/. The caller knows both: it
    passed the id, and the side came from the artifact row.
    """
    return Chunk(
        text=stored.text,
        source=stored.source,
        start_line=stored.start_line,
        end_line=stored.end_line,
        side=side,
        artifact_id=artifact_id,
        chunk_index=stored.chunk_index,
        header=stored.header,
    )
