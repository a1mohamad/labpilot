"""Merged reranking against per-side reranking. Never measured.

    PYTHONPATH=. python scripts/bench_merged.py quora
    PYTHONPATH=. python scripts/bench_merged.py quora cobra+log

CLAUDE.md decided PER SIDE in section 10c and said plainly why it was not
evidence:

    "SLICE 8 OWES THIS MEASUREMENT: merged against per side, on the same
     corpus. It is a real question and it is not settled by the argument
     above - merged halves the rerank cost, and the rerank budget is the
     tightest one in the project once verify needs a call per claim.
     Per side is the DEFAULT, not the answer."

The two differ in what they can lose:

    per side   2 calls of SEARCH_LIMIT documents. Coverage is STRUCTURAL:
               each side is guaranteed its own slots, whatever the scores say.
    merged     1 call of 2 x SEARCH_LIMIT. Half the calls and half the
               latency - and one side can take every slot.

So the measurement is not "which scores higher overall". It is **how often
does merged starve a side**, because that is the failure per-side exists to
make impossible, and a mean over queries hides it completely.

A comparison needs TWO artifacts. `quora` is the only fixture that ships as a
pair; for the rest a pair is built by joining two corpora, which is a harsher
test than the real case - two unrelated projects share no vocabulary, so the
scores are as separable as they will ever be.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv

from labpilot.store.defaults import SEARCH_LIMIT
from scripts.score_hybrid import CORPORA, targets
from scripts.score_rerank import (
    RERANKERS,
    PairScores,
    cached_vectors,
    dense_orders,
)

RESULTS = Path(".logs/results")
TOP_N = 10


def sides(name: str):
    """Two sides, and the queries that belong to each.

    `a+b` joins two corpora into one comparison. Chunk ids are renumbered so
    that side B's positions continue after side A's, exactly as assign_ids
    does in the real prompt - and the ground truth moves with them.
    """
    if "+" in name:
        first, second = name.split("+")
        a_chunks, a_queries = CORPORA[first]()
        b_chunks, b_queries = CORPORA[second]()
        return (a_chunks, a_queries), (b_chunks, b_queries)

    chunks, queries = CORPORA[name]()
    half = len(chunks) // 2
    return (chunks[:half], queries), (chunks[half:], queries)


def order_for(pairs, query, candidates, documents):
    pairs.fetch(query, sorted(candidates), documents)
    return pairs.order(query.id, candidates)


def run(name: str, model_key: str) -> None:
    (a_chunks, a_queries), (b_chunks, b_queries) = sides(name)
    a_name, b_name = (name.split("+") + [name])[:2] if "+" in name else (name, name)

    reranker = RERANKERS[model_key]
    rows = []

    merged_chunks = list(a_chunks) + list(b_chunks)
    offset = len(a_chunks)
    documents = [c.embed_text for c in merged_chunks]

    if a_name == b_name:
        # One corpus cut in half. The cache holds the WHOLE corpus, so ask for
        # the whole length - the freshness guard compares against what the
        # corpus really has, and half of it is not a stale cache.
        whole = cached_vectors(
            a_name, "codestral-embed", "chunks", len(a_chunks) + len(b_chunks)
        )
        a_vec, b_vec = whole[: len(a_chunks)], whole[len(a_chunks) :]
    else:
        a_vec = cached_vectors(a_name, "codestral-embed", "chunks", len(a_chunks))
        b_vec = cached_vectors(b_name, "codestral-embed", "chunks", len(b_chunks))

    # SIDE A ASKS, and both sides are searched for the SAME question - which is
    # what a comparison does. So side B is ranked with side A's query vectors,
    # never with its own queries: a query id that exists on one side and not
    # the other is not a fixture problem, it is the wrong question being asked.
    a_q = cached_vectors(a_name, "codestral-embed", "queries", len(a_queries))
    dense_a = dense_orders(a_queries, a_q, a_vec)
    dense_b = dense_orders(a_queries, a_q, b_vec)
    queries = a_queries

    import scripts.score_rerank as sr

    sr.RERANKER = reranker
    pairs = PairScores(f"merged_{name}", "")

    starved = 0
    per_side_hits, merged_hits = [], []
    for query in queries:
        top_a = [i for i, _ in dense_a[query.id][:SEARCH_LIMIT]]
        top_b = [i for i, _ in dense_b[query.id][:SEARCH_LIMIT]]

        # PER SIDE: each side reranked alone, then each keeps half the slots.
        kept_a = order_for(pairs, query, top_a, [c.embed_text for c in a_chunks])
        kept_b = order_for(pairs, query, top_b, [c.embed_text for c in b_chunks])
        per_side = [("A", i) for i in kept_a[: TOP_N // 2]]
        per_side += [("B", i) for i in kept_b[: TOP_N // 2]]

        # MERGED: one call over both sides' candidates, top N wins outright.
        pool = top_a + [i + offset for i in top_b]
        kept = order_for(pairs, query, pool, documents)[:TOP_N]
        merged = [("A", i) if i < offset else ("B", i - offset) for i in kept]

        from_a = sum(1 for side, _ in merged if side == "A")
        if from_a == 0 or from_a == len(merged):
            starved += 1

        want_a = targets(a_chunks, query)
        per_side_hits.append(any(i in want_a for side, i in per_side if side == "A"))
        merged_hits.append(any(i in want_a for side, i in merged if side == "A"))
        rows.append({"query": query.id, "from_a": from_a, "of": len(merged)})

    print(f"\n{name}: {len(queries)} queries, {len(a_chunks)}+{len(b_chunks)} chunks")
    print(f"  rerank calls: per side 2 per query, merged 1 - {pairs.calls} spent here")
    shares = [r["from_a"] / r["of"] for r in rows]
    print(
        f"  merged gave side A {statistics.mean(shares):.0%} of the slots "
        f"(min {min(shares):.0%}, max {max(shares):.0%})"
    )
    print(f"  merged STARVED one side entirely on {starved} of {len(rows)} queries")
    print(
        f"  side A's answer in the kept set: per side "
        f"{sum(per_side_hits) / len(per_side_hits):.3f}, "
        f"merged {sum(merged_hits) / len(merged_hits):.3f}"
    )

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"merged_{name.replace('+', '_')}.json").write_text(
        json.dumps(
            {
                "pair": name,
                "queries": len(queries),
                "starved": starved,
                "mean_share_a": statistics.mean(shares),
                "min_share_a": min(shares),
                "per_side_hit": sum(per_side_hits) / len(per_side_hits),
                "merged_hit": sum(merged_hits) / len(merged_hits),
                "rows": rows,
            },
            indent=1,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    load_dotenv(".env")
    if len(sys.argv) < 2:
        raise SystemExit(f"usage: {sys.argv[0]} <corpus|a+b> [--model=flashlite]")
    model = next(
        (a.split("=")[1] for a in sys.argv if a.startswith("--model=")), "flashlite"
    )
    for target in [a for a in sys.argv[1:] if not a.startswith("--")]:
        run(target, model)
