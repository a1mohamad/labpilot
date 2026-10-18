from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator, Sequence

import psycopg

from labpilot.api.contracts import Ingested
from labpilot.api.errors import (
    EmbeddingUnavailable,
    EmptyArtifact,
    UnreadableUpload,
)
from labpilot.api.source_chunks import chunk_source
from labpilot.embed import (
    MIGRATION,
    EmbeddingError,
    HTTPEmbedder,
    by_speed,
    embed_batches,
)
from labpilot.ingest import (
    Chunk,
    LoaderError,
    Side,
    chunk_bytes,
)
from labpilot.sources import Source
from labpilot.store import (
    ArtifactRecord,
    ChunkRecord,
    write_artifact,
)
from labpilot.tokens import estimate_tokens

# How long an ingest may take before we stop optimising for QUALITY and start
# optimising for TIME. NOT a refusal: past this line the same list is sorted by
# speed instead of by strength, and a slow model is still used when every fast
# one is spent - the user is shown the estimate and asked first.
EMBEDDING_MINUTES_BUDGET = 6.0

# WHAT THE INGEST ESTIMATE WAS MISSING, measured 2026-09-19 by
# scripts/bench_ingest.py over five real corpora, 213 to 1,506 chunks:
#
#   corpus      chunks   MEASURED  PREDICTED  ratio   gap per chunk
#   websocket      213     18.3s      10.2s   1.8x        0.038s
#   log            308     21.4s      12.3s   1.7x        0.030s
#   cobra          598     42.2s      27.2s   1.6x        0.025s
#   requests       334     21.4s       8.9s   2.4x        0.037s
#   geo           1506    105.7s      77.3s   1.4x        0.019s
#
# `embedding_minutes()` models EMBEDDING THROUGHPUT and nothing else, so it was
# optimistic by 1.4-2.4x on every corpus - and it is the number the page
# renders. We were telling a user "~6 min" for an 11-minute wait.
#
# The gap is ~0.030s per chunk and it is OUR work, not the provider's:
# chunking, and the write transaction. That is why it is added here rather than
# inside embed/ - it is the same for every embedder, so adding it there would
# have blurred the one thing that estimate exists to compare.
INGEST_OVERHEAD_SECONDS = 0.030

# When to STOP and ask the user, against the CORRECTED estimate above.
#
# 2.0 STAYS, and the threshold was never the defect - the number it was
# compared against was. Re-checked on the same five corpora, the correction
# lands the estimate within +-14% instead of 40-60% short:
#
#   corpus      chunks  measured     was          NOW
#   websocket      213     18.3s   10.2s 1.8x   16.6s 1.1x
#   log            308     21.4s   12.3s 1.7x   21.5s 1.0x
#   cobra          598     42.2s   27.2s 1.6x   45.1s 0.9x
#   requests       334     21.4s    8.9s 2.4x   18.9s 1.1x
#   geo           1506    105.7s   77.3s 1.4x  122.5s 0.9x
#
# At the project's own 236 tokens/chunk the warning now fires above ~2,150
# chunks: quiet for a notebook, loud for a repository, which is the behaviour a
# warning needs to be worth reading.
#
#   1,000 chunks   0.9 min   quiet
#   2,200 chunks   2.0 min   WARNED
#  10,000 chunks   9.3 min   WARNED
#
# Note it still reads slightly LOW at the largest size measured (0.9x on geo),
# so 10,000 chunks is likely nearer 11 minutes than 9. Recorded rather than
# padded: a fudge factor on top of a measured one would make the next person
# unable to tell which part was measured.
#
# STILL NOT A TOTAL, and the label must keep saying so: a report is another
# 2-8 minutes on top, measured 2026-09-19 at 119s, 401s and 488s on three runs
# of the SAME model and machine. Warning on a true end-to-end total needs a
# stable generation time, and three samples spanning 4x is not one.
WARN_MINUTES = 2.0

# SMALL_CORPUS_CHUNKS WAS HERE AND IS DELETED - 2026-09-18.
#
# It routed any corpus under 500 chunks to Google first, on the v2 finding that
# "Google retrieves best where vector search is already easy". That rested on
# THREE corpora. Re-measured on six, against `gemini-embedding-001` (the model
# that matters after the MIGRATION fix in embed/registry.py):
#
#     corpus      chunks  codestral  gemini-001
#     websocket       78    0.668      0.530     codestral +0.138
#     quora           82    0.608      0.674     google    +0.066
#     disaster       108    0.753      0.760     google    +0.006
#     titanic        118    0.594      0.537     codestral +0.057
#     requests       335    0.646      0.650     google    +0.004
#     lung           628    0.587      0.569     codestral +0.019
#
# THREE WINS EACH, and net codestral ahead by 0.023 MRR - about half a query on
# a 20-query fixture, which is BELOW what these fixtures can resolve. So the
# rule bought no measurable quality, while costing:
#
#   19x slower than codestral at every size (4.1 min against 0.21 at 500)
#   it tripped its own WARN_MINUTES = 2.0, so the router chose an embedder the
#     UI then had to apologise for
#   1,000 TEXTS a day, exhausted by a single 943-chunk run while measuring this
#
# A rule that exists to buy quality, and buys none, is deleted rather than
# retuned. MIGRATION's own order now decides, and codestral leads it on
# measured recall - 19 of 20 corpora against mistral-embed.


def ingest_artifact(
    conn: psycopg.Connection,
    raw: bytes,
    *,
    name: str,
    side: Side,
    field: str = "artifact",
) -> Ingested:
    """Turn an uploaded file into rows in pgvector.

    Entry is the only layer allowed to import ingest/, embed/ AND store/, so
    the translation between their three vocabularies lives here by the layering
    rule rather than by preference:

        Chunk (ingest) + Vector (embed) -> ChunkRecord (store)

    The connection is passed IN, matching write_artifact and search. So a
    failure to reach the database happens in the caller, never here.
    """
    artifact_id = _artifact_id(raw, side)
    chunks = _cut_bytes(raw, name=name, side=side, artifact_id=artifact_id, field=field)

    return _store(conn, chunks, artifact_id=artifact_id, name=name, side=side)


def ingest_source(conn: psycopg.Connection, source: Source, *, side: Side) -> Ingested:
    """A whole folder, archive or repository, stored as ONE artifact.

    The walk counts what it skipped rather than dropping it - a repository is
    the case where one unreadable file used to abort the entire ingest, twice,
    silently, because a generator stops at the first raise.
    """
    chunks = tuple(chunk_source(source, side=side))
    if not chunks:
        raise EmptyArtifact(f"{source.name} holds no text we can read")

    artifact_id = _source_id(chunks, side)
    return _store(conn, chunks, artifact_id=artifact_id, name=source.name, side=side)


def _store(
    conn: psycopg.Connection,
    chunks: Sequence[Chunk],
    *,
    artifact_id: str,
    name: str,
    side: Side,
) -> Ingested:
    """Pick an embedder, embed, and write - shared by both ingest doors.

    Extracted when the repository door arrived rather than duplicated, because
    the two doors differ ONLY in how they get chunks. Slice 3 was bitten twice
    by two doors drifting apart on exactly this kind of shared step.
    """
    tokens = sum(estimate_tokens(chunk.embed_text) for chunk in chunks)
    embedder, minutes = _pick_embedder(tokens=tokens, chunks=len(chunks))
    artifact = ArtifactRecord(
        id=artifact_id,
        name=name,
        side=side,
        embedding_model=embedder.model,
        dim=embedder.dim,
    )

    try:
        written = write_artifact(conn, artifact, _records(embedder, chunks))
    except EmbeddingError as exc:
        raise EmbeddingUnavailable(f"{embedder.name}: {exc}") from exc

    return Ingested(artifact=artifact, chunks=written, ingest_minutes=minutes)


def _source_id(chunks: Sequence[Chunk], side: Side) -> str:
    """The CONTENT decides the id, as it does for a single file.

    Hashed from what was really read - each file's path and text - rather than
    from the archive's bytes, so the same repository arriving as a zip and as a
    git URL is ONE artifact and re-ingesting replaces it.
    """
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk.source.encode("utf-8"))
        digest.update(chunk.text.encode("utf-8"))

    return f"{side}-{digest.hexdigest()[:16]}"


def _artifact_id(raw: bytes, side: Side) -> str:
    """The CONTENT decides the id, so re-ingesting the same file replaces it.

    write_artifact deletes before inserting, so a stable id makes ingest
    idempotent: upload the same paper twice and you get one corpus, not two.
    The side is part of the id because one file can legitimately be both the
    reference and the subject.
    """
    return f"{side}-{hashlib.sha256(raw).hexdigest()[:16]}"


def _pick_embedder(
    *, tokens: int, chunks: int, candidates: Sequence[HTTPEmbedder] = MIGRATION
) -> tuple[HTTPEmbedder, float]:
    """ONE list, sorted two ways - by strength normally, by speed when slow.

    MIGRATION is already the strength order. If its best model would take
    longer than the budget, the SAME list is re-sorted by speed. Nothing is
    ever dropped, so the walk cannot dead-end; only a model's place moves. A
    two-pool version was considered first and was wrong for exactly that
    reason: two fast models, both spent, and nowhere left to go.

    A model that cannot finish TODAY reports infinite time and is skipped,
    which is how Cloudflare's daily neuron budget removes BGE from a large
    corpus without needing a second mechanism.

    THERE IS NO LONGER A SPECIAL CASE FOR SMALL CORPORA. One used to send
    anything under 500 chunks to Google first; it was re-measured on six
    corpora in slice 8 v3, found to buy no resolvable quality, and deleted -
    the numbers are above the constants at the top of this file.
    """
    order = candidates
    if (
        order[0].embedding_minutes(tokens=tokens, chunks=chunks)
        > EMBEDDING_MINUTES_BUDGET
    ):
        order = by_speed(tokens=tokens, chunks=chunks, candidates=candidates)

    for embedder in order:
        minutes = embedder.embedding_minutes(tokens=tokens, chunks=chunks)
        if minutes != math.inf:
            # The ORDERING above uses the embedding estimate, because that is
            # the part that differs between models. What we RETURN is the whole
            # ingest, because that is what the caller waits through and what
            # the page renders.
            return embedder, minutes + chunks * INGEST_OVERHEAD_SECONDS / 60

    raise EmbeddingUnavailable(
        f"no embedder can ingest {chunks} chunks ({tokens} tokens) today"
    )


def _records(embedder: HTTPEmbedder, chunks: Sequence[Chunk]) -> Iterator[ChunkRecord]:
    """Chunk + vector -> ChunkRecord, one batch at a time.

    A GENERATOR on purpose. 2,000 vectors of 1,536 floats held as Python lists
    is ~73MB against a 512MB box that is also serving the API; yielding per
    batch keeps the peak near 5MB. write_artifact consumes this INSIDE one
    transaction, so streaming and atomicity do not conflict - streaming is
    about Python objects, the transaction is about the database. Either all
    2,000 rows land or none do.
    """
    texts = [chunk.embed_text for chunk in chunks]
    index = 0
    for batch in embed_batches(embedder, texts):
        for vector in batch.vectors:
            chunk = chunks[index]
            yield ChunkRecord(
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                header=chunk.header,
                source=chunk.source,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                vector=vector,
            )
            index += 1


def _cut_bytes(
    raw: bytes, *, name: str, side: Side, artifact_id: str, field: str
) -> tuple[Chunk, ...]:
    """The loader-error mapping, shared by both doors.

    Extracted so the upload path and the ingest path cannot drift apart: the
    same bad .ipynb must become the same 422 whichever door it arrives at.
    Slice 3 was bitten twice by exactly that - one door was fixed and the
    other silently mangled notebooks.
    """
    try:
        chunks = chunk_bytes(raw, source=name, side=side, artifact_id=artifact_id)
    except LoaderError as exc:
        raise UnreadableUpload(f"{field} ({name}): {exc}") from exc
    if not chunks:
        raise EmptyArtifact(f"{field} ({name}) holds no text")

    return chunks
