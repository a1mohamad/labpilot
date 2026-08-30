"""Re-score queries.json after any change that moves chunk boundaries.

CLAUDE.md calls queries.json the instrument for the whole of Step 1 and says to
re-score after every retrieval change. Slice 1's scorer lived in a session
scratchpad and was lost, so the overlap fix had to rewrite it from nothing.
This is that script, kept.

    PYTHONPATH=. python scripts/score_retrieval.py

Costs four embedding requests and no generation quota. Ground truth is stored
as LINE NUMBERS, so it survives any change to chunking: a query is answered by
whichever chunk happens to contain one of its lines.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from labpilot.embed import CODESTRAL_EMBED, MAX_BATCH_SIZE
from labpilot.ingest import chunk_file

SAMPLES = Path("data/samples/quora_siamese")

# Measured 2026-08-20 on 78 chunks, reproduced 2026-08-27 as a control.
BASELINE = "slice 1 baseline: recall@1 0.412  @5 0.941  @10 0.941  MRR 0.613"


def cosine(one: tuple[float, ...], other: tuple[float, ...]) -> float:
    # Every vector leaving labpilot.embed is normalised, so a dot product is
    # the cosine. That is the whole reason we normalise there and not here.
    return sum(a * b for a, b in zip(one, other, strict=True))


def answered_by(chunks, expects: list[int]) -> set[int]:
    return {
        index
        for index, chunk in enumerate(chunks)
        if any(chunk.start_line <= line <= chunk.end_line for line in expects)
    }


def main() -> int:
    load_dotenv(".env")
    if not os.getenv("MISTRAL_API_KEY"):
        print("MISTRAL_API_KEY is not set", file=sys.stderr)
        return 1

    chunks = chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="quora")
    queries = json.loads((SAMPLES / "queries.json").read_text(encoding="utf-8"))
    print(f"corpus {len(chunks)} chunks   queries {len(queries)}")

    stored: list[tuple[float, ...]] = []
    for start in range(0, len(chunks), MAX_BATCH_SIZE):
        batch = chunks[start : start + MAX_BATCH_SIZE]
        stored.extend(CODESTRAL_EMBED.embed([c.embed_text for c in batch]).vectors)
    asked = CODESTRAL_EMBED.embed([q["query"] for q in queries], task="query").vectors

    ranks: list[tuple[str, int]] = []
    for query, vector in zip(queries, asked, strict=True):
        wanted = answered_by(chunks, query["expects"])
        order = sorted(
            range(len(chunks)), key=lambda i: cosine(vector, stored[i]), reverse=True
        )
        place = next(
            (rank for rank, i in enumerate(order, 1) if i in wanted), len(chunks) + 1
        )
        ranks.append((query["id"], place))

    for query_id, place in ranks:
        print(f"  {query_id:5} rank {place}")

    def recall(k: int) -> float:
        return sum(1 for _, place in ranks if place <= k) / len(ranks)

    mrr = sum(1 / place for _, place in ranks) / len(ranks)
    print(
        f"\nrecall@1 {recall(1):.3f}  @5 {recall(5):.3f}  "
        f"@10 {recall(10):.3f}  MRR {mrr:.3f}"
    )
    print(BASELINE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
