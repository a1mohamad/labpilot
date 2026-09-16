"""Merged reranking against per-side, which is slice 8 job 5.

`_retrieved()` reranks each side on its own and never merges. Merged would
halve the rerank cost and hand one call 100 documents - which Cohere bills as
ONE search unit, so on that provider merged is literally half price. What it
risks is COVERAGE: one side can take every slot, and a comparison with one
side is not a comparison.

CLAUDE.md chose per-side on an argument - "a guarantee in the shape beats a
guarantee in a downstream rule" - and explicitly recorded that it is the
DEFAULT, not the answer. This measures it.

    PYTHONPATH=. python scripts/bench_merged.py [n_queries]

THE SETUP IS A DELIBERATE FAKE PAIR. geo is side B and holds every answer;
requests is side A and holds NONE of them. That is the worst case on purpose:
if merged can lose the answer, a side whose chunks are all irrelevant is
where it happens. A real pair would be kinder and would tell us less.

Two numbers come out:

    survival   does the true chunk still reach the prompt?
    balance    how many of the merged slots go to each side? A merged call
               that hands 20 of 20 to one side has lost the comparison even
               when it kept the answer.
"""

from __future__ import annotations

import pickle
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from labpilot.rerank import RerankError
from scripts.score_hybrid import CORPORA, targets
from scripts.score_rerank import RERANKERS

CACHE = Path(".cache/hybrid")
MODEL = "codestral-embed"
WINDOW = 50
PER_SIDE_TOP_N = 10
PACE = 4.5


def dense_top(vectors, query_vector, limit: int) -> list[int]:
    scored = [
        (i, sum(a * b for a, b in zip(query_vector, v, strict=True)))
        for i, v in enumerate(vectors)
    ]
    scored.sort(key=lambda kv: (-kv[1], kv[0]))
    return [i for i, _ in scored[:limit]]


def main(n: int = 45) -> int:
    load_dotenv(".env")
    reranker = RERANKERS["flashlite"]

    b_chunks, queries = CORPORA["geo"]()
    a_chunks, _ = CORPORA["requests"]()
    b_vecs = pickle.loads((CACHE / f"geo_{MODEL}_chunks.pkl").read_bytes())
    a_vecs = pickle.loads((CACHE / f"requests_{MODEL}_chunks.pkl").read_bytes())
    q_vecs = pickle.loads((CACHE / f"geo_{MODEL}_queries.pkl").read_bytes())

    queries, q_vecs = queries[:n], q_vecs[:n]
    per_side_hits, merged_hits, merged_share, failures = 0, 0, [], 0

    for query, qv in zip(queries, q_vecs, strict=True):
        want = targets(b_chunks, query)
        b_top = dense_top(b_vecs, qv, WINDOW)
        a_top = dense_top(a_vecs, qv, WINDOW)

        # PER SIDE: side B is reranked alone, so its ten slots are its own.
        try:
            order = reranker.rank(
                query.text, [b_chunks[i].embed_text for i in b_top]
            ).order
        except RerankError as exc:
            print(f"  {query.id} per-side FAILED {str(exc)[:70]}")
            failures += 1
            continue
        kept = [b_top[p] for p in order[:PER_SIDE_TOP_N]]
        per_side_hits += bool(want & set(kept))
        time.sleep(PACE)

        # MERGED: both sides in ONE call, and twice the slots, so the total
        # sent to the prompt is identical. Only the guarantee differs.
        docs = [b_chunks[i].embed_text for i in b_top] + [
            a_chunks[i].embed_text for i in a_top
        ]
        try:
            order = reranker.rank(query.text, docs).order
        except RerankError as exc:
            print(f"  {query.id} merged FAILED {str(exc)[:70]}")
            failures += 1
            continue
        top = order[: PER_SIDE_TOP_N * 2]
        from_b = [b_top[p] for p in top if p < WINDOW]
        merged_hits += bool(want & set(from_b))
        merged_share.append(len(from_b) / max(1, len(top)))
        time.sleep(PACE)

        print(
            f"  {query.id} per-side {'HIT ' if want & set(kept) else 'miss'}"
            f"  merged {'HIT ' if want & set(from_b) else 'miss'}"
            f"  B took {len(from_b)}/{len(top)}",
            flush=True,
        )

    done = len(merged_share)
    print(f"\n  {done} queries scored, {failures} failed")
    print(f"  per-side  answer reached the prompt: {per_side_hits}/{done}")
    print(f"  merged    answer reached the prompt: {merged_hits}/{done}")
    if merged_share:
        print(
            f"  merged slot share for the side that HAS the answer: "
            f"mean {statistics.mean(merged_share):.2f}, "
            f"min {min(merged_share):.2f}, max {max(merged_share):.2f}"
        )
        starved = sum(1 for s in merged_share if s in (0.0, 1.0))
        print(f"  calls where ONE side took every slot: {starved}/{done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 45))
