"""Put a scored corpus into the real database, reusing the cached vectors.

Slice 8 job 3 asks whether exact search is still the right call on REAL
artifacts, and job 4 asks what the whole pipeline costs in wall clock. Both
need rows in Postgres, and re-embedding to get them would spend quota on
vectors that are already sitting in .cache/hybrid.

    PYTHONPATH=. python scripts/load_corpus.py geo codestral-embed

Writes through `write_artifact`, so this exercises the real write path - the
leading DELETE, the batching, and the single transaction - rather than a
shortcut that would measure something we do not ship.
"""

from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from labpilot.store import ArtifactRecord, ChunkRecord, connect, write_artifact

CACHE = Path(".cache/hybrid")


def main(corpus: str, model: str) -> int:
    """`corpus` may be several names joined by "+", which loads them as ONE
    artifact. Slice 8 needs a row count in the range the project targets and
    no single fixture reaches it; the vectors are still real and clustered,
    which is the property the 2026-09-05 benchmark lacked twice."""
    from scripts.score_hybrid import CHUNK_LOADERS

    chunks, vectors = [], []
    for part in corpus.split("+"):
        got = CHUNK_LOADERS[part]()
        vecs = pickle.loads((CACHE / f"{part}_{model}_chunks.pkl").read_bytes())
        if len(vecs) != len(got):
            raise SystemExit(f"{part}: {len(vecs)} vectors for {len(got)} chunks")
        chunks.extend(got)
        vectors.extend(vecs)

    artifact = ArtifactRecord(
        id=f"B-bench-{corpus.replace(chr(43), chr(45))}",
        name=corpus,
        side="B",
        embedding_model=model,
        dim=len(vectors[0]),
    )
    # RENUMBER, exactly as chunk_source does. chunk_file numbers what IT
    # produced, so chunk_index restarts at 0 in every file and a 72-file
    # corpus collides on the primary key at the second one. The position in
    # this list is also what score_hybrid's `targets()` uses, so renumbering
    # here keeps the database and the fixture talking about the same chunk.
    records = (
        ChunkRecord(
            chunk_index=i,
            text=c.text,
            header=c.header,
            source=c.source,
            start_line=c.start_line,
            end_line=c.end_line,
            vector=tuple(v),
        )
        for i, (c, v) in enumerate(zip(chunks, vectors, strict=True))
    )

    started = time.time()
    with connect() as conn:
        written = write_artifact(conn, artifact, records)
    print(
        f"{artifact.id}: {written} chunks, dim {artifact.dim}, "
        f"{time.time() - started:.1f}s"
    )
    return 0


if __name__ == "__main__":
    load_dotenv(".env")
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
