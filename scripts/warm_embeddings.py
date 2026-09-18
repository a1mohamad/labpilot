"""Fill the embedding cache for one corpus and one model, and nothing else.

Chunk vectors do not depend on the query set, so the slow models can be paid
for while the fixture is still being written. Writes the SAME file
score_hybrid.py reads, so a later scoring run finds it and spends nothing.

    PYTHONPATH=. python scripts/warm_embeddings.py geo gemini-embedding-001

Google enforces its published 30,000 tokens/minute exactly, so a 345k-token
corpus is ~14 minutes of wall clock that is almost all sleeping. Run it in the
background and do something else.
"""

from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from labpilot.embed import MIGRATION, EmbeddingError, embed_batches
from labpilot.tokens import estimate_tokens

CACHE = Path(".cache/hybrid")
# Only where the provider really enforces one. A model that is not here is
# sent as fast as it will take it, which is what the 2026-09-14 measurement
# found codestral and mistral-embed actually allow.
# Texts per minute, where the provider counts TEXTS. Google does; nobody
# else here has been shown to.
TEXTS_PER_MINUTE = {"gemini-embedding-001": 100, "gemini-embedding-2": 100}

PACED = {
    "gemini-embedding-001": 30_000,
    "gemini-embedding-2": 30_000,
    # MEASURED 2026-09-16 by hitting it: "trial token rate limit exceeded,
    # limit is 100000 tokens per minute". Recorded NOWHERE in this project -
    # the registry carries only Cohere's 10 requests/minute, and its
    # measured_tokens_per_minute of 640,000 was a BURST that never met a
    # limit. The real ceiling is 6.4x smaller.
    "embed-v4.0": 100_000,
}


def warm(corpus: str, model: str) -> int:
    from scripts.score_hybrid import CHUNK_LOADERS

    chunks = CHUNK_LOADERS[corpus]()
    texts = [c.embed_text for c in chunks]
    embedder = next(e for e in MIGRATION if e.model == model)

    CACHE.mkdir(parents=True, exist_ok=True)
    # A model name can contain SLASHES - BGE is "@cf/baai/bge-base-en-v1.5"
    # - which turns the cache filename into a PATH and the write into a
    # FileNotFoundError. Measured 2026-09-18: the embedding SUCCEEDED, 89 of
    # 89 vectors and 17,807 tokens spent, and then the result was thrown away
    # on the write. score_rerank already sanitised this; the embed path did
    # not, which is part of why BGE had never been scored.
    out = CACHE / f"{corpus}_{model.replace('/', '_')}_chunks.pkl"
    if out.exists():
        print(f"already cached: {out}")
        return 0

    # BATCH BY TOKENS, NOT BY COUNT - measured 2026-09-16 and it is finding
    # F1. A 96-text batch of geo chunks is ~44,500 estimated tokens, and
    # Google refuses a single call larger than its 30,000/minute bucket
    # however long you wait: 96 -> 429, then 40 -> 200 immediately after, so
    # the call was refused for its own SIZE and not for an empty bucket.
    #
    # Target ~45% of the budget per request, so two fit in a minute.
    budget = PACED.get(model)
    per_request = int(budget * 0.45) if budget else None
    # CONTENTS per minute, not calls per minute - finding F4. Google counts
    # each text in a batchEmbedContents call as one request, proven by three
    # 40-text calls in six seconds hitting a limit of 100.
    per_minute = TEXTS_PER_MINUTE.get(model)

    vectors: list = []
    spent, sent, window, started = 0, 0, time.time(), time.time()
    start = 0
    while start < len(texts):
        step = 96
        if per_request:
            step, cost = 0, 0
            while start + step < len(texts) and step < 96:
                nxt = estimate_tokens(texts[start + step])
                if step and cost + nxt > per_request:
                    break
                cost, step = cost + nxt, step + 1
            step = max(1, step)
        batch = texts[start : start + step]
        cost = sum(estimate_tokens(t) for t in batch)

        if (budget and spent + cost > budget * 0.9) or (
            per_minute and sent + len(batch) > per_minute * 0.9
        ):
            time.sleep(max(0.0, 62 - (time.time() - window)))
            spent, sent, window = 0, 0, time.time()

        # `backend_out_of_capacity` is Mistral saying "busy", not "spent" -
        # HTTP 429 code 3505, and it killed two corpora mid-run on the first
        # pass. embed_batches only halves on a refusal that names TOKENS, and
        # this one names capacity, so it raises instead. The five-way rule
        # applies here as much as it does to generation: a 429 that resets in
        # seconds is a wait, not a dead pool.
        #
        # A read timeout is the same class and was measured the same day:
        # DEFAULT_TIMEOUT allows 10 seconds to CONNECT, and this VPN link
        # carrying three jobs at once did not always manage it.
        for wait in (5, 15, 40, 90, None):
            try:
                for got in embed_batches(embedder, batch, size=len(batch)):
                    vectors.extend(got.vectors)
                break
            except EmbeddingError as exc:
                transient = ("capacity" in str(exc)) or ("timed out" in str(exc))
                if wait is None or not transient:
                    raise
                print(f"  busy, waiting {wait}s", flush=True)
                time.sleep(wait)
        spent += cost
        sent += len(batch)
        start += step
        print(f"  {model} {len(vectors)}/{len(texts)}  (+{cost} tok)", flush=True)

    out.write_bytes(pickle.dumps(vectors))
    print(f"wrote {out}  {len(vectors)} vectors  {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    load_dotenv(".env")
    raise SystemExit(warm(sys.argv[1], sys.argv[2]))
