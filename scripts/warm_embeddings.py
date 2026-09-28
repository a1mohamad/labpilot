"""Fill the embedding cache for one corpus and one model, and nothing else.

Chunk vectors do not depend on the query set, so the slow models can be paid
for while the fixture is still being written. Writes the SAME file
score_hybrid.py reads, so a later scoring run finds it and spends nothing.

    PYTHONPATH=. python scripts/warm_embeddings.py geo gemini-embedding-001

Google enforces its published 30,000 tokens/minute exactly, so a 345k-token
corpus is ~14 minutes of wall clock that is almost all sleeping. Run it in the
background and do something else.

Batching, pacing and waiting out a 429 or 503 all come from the PRODUCT's
`embed_batches` - this script used to carry its own copy, written before the
product could do it, which meant the instrument measured code we did not ship.
"""

from __future__ import annotations

import pickle
import sys
import time
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from labpilot.embed import MIGRATION, EmbeddingError, Pace, embed_batches

CACHE = Path(".cache/hybrid")

# MEASURED 2026-09-16 by hitting it: "trial token rate limit exceeded, limit is
# 100000 tokens per minute". The registry does not carry it - Cohere's embedder
# has no Pace - so it is added here, for the one run that needs it.
SCRIPT_PACES = {"embed-v4.0": Pace(tokens_per_minute=100_000)}

# `embed_batches` waits out a 429 or 503, but a READ TIMEOUT has no status and
# is raised. Measured 2026-09-16: this VPN link carrying three jobs at once did
# not always connect within DEFAULT_TIMEOUT's 10 seconds. Nothing already
# embedded is lost - the next attempt resumes where the last one stopped.
TIMEOUT_WAITS = (15.0, 40.0, 90.0)


def warm(corpus: str, model: str) -> int:
    from scripts.score_hybrid import CHUNK_LOADERS

    chunks = CHUNK_LOADERS[corpus]()
    texts = [c.embed_text for c in chunks]
    embedder = next(e for e in MIGRATION if e.model == model)
    if model in SCRIPT_PACES:
        embedder = replace(embedder, pace=SCRIPT_PACES[model])

    CACHE.mkdir(parents=True, exist_ok=True)
    # A model name can contain SLASHES - BGE is "@cf/baai/bge-base-en-v1.5"
    # - which turns the cache filename into a PATH and the write into a
    # FileNotFoundError. Measured 2026-09-18: the embedding SUCCEEDED, 89 of
    # 89 vectors and 17,807 tokens spent, and then the result was thrown away
    # on the write.
    out = CACHE / f"{corpus}_{model.replace('/', '_')}_chunks.pkl"
    if out.exists():
        print(f"already cached: {out}")
        return 0

    vectors: list = []
    started = time.time()
    waits = iter(TIMEOUT_WAITS)
    while len(vectors) < len(texts):
        try:
            for batch in embed_batches(embedder, texts[len(vectors) :]):
                vectors.extend(batch.vectors)
                print(f"  {model} {len(vectors)}/{len(texts)}", flush=True)
        except EmbeddingError as exc:
            wait = next(waits, None)
            if exc.status is not None or "timed out" not in str(exc) or wait is None:
                raise
            print(f"  timed out, waiting {wait:.0f}s, then resuming", flush=True)
            time.sleep(wait)

    out.write_bytes(pickle.dumps(vectors))
    print(f"wrote {out}  {len(vectors)} vectors  {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    load_dotenv(".env")
    raise SystemExit(warm(sys.argv[1], sys.argv[2]))
