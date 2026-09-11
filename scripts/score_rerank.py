"""Does reranking help, how many chunks to send, and is the gate worth having.

The four measurements slice 6 owes before it closes. A measurement you cannot
repeat is a number, not a result, which is why this sits in the repository
beside score_retrieval.py and score_hybrid.py.

    PYTHONPATH=. python scripts/score_rerank.py quora codestral
    PYTHONPATH=. python scripts/score_rerank.py requests google --fusion

Embeddings come from score_hybrid's cache, so the embedder costs NOTHING here.
Rerank scores are cached PER (query, chunk) PAIR rather than per call, which is
what makes a re-run free: a cross-encoder scores one pair at a time, so the
same pair needed by a different candidate set is already paid for.

The instrument is Cloudflare's bge-reranker-base: ~3.52 neurons per 50-document
call against 10,000 a DAY, which is the largest renewing budget we have. Cohere
is deliberately NOT used - its 1,000 a month is the chain primary's own bucket.

What this run may NOT conclude, carried forward from slice 5: which provider is
best (slice 8), that the chain-3 order is settled (slice 8), or that fusion is
dead. And the fixture may REJECT, never CONFIRM - the headroom at k=10 is about
0.064, so one query on the 45-query corpus is a third of it.
"""

from __future__ import annotations

import json
import os
import pickle
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from labpilot.rerank import CLOUDFLARE_RERANK, VOYAGE_RERANK
from labpilot.retrieval.gate import margin
from labpilot.store.defaults import SEARCH_LIMIT
from scripts.score_hybrid import CORPORA, EMBEDDERS, bm25, keyword_signals, rrf, targets

CACHE = Path(".cache/rerank")
EMBED_CACHE = Path(".cache/hybrid")

# Cohere is deliberately absent: 1,000 calls a MONTH is the chain primary's own
# bucket, shared with chat and embed, and one measurement run is 45 calls.
# Cloudflare is the default because ~2,840 a day cannot realistically run out;
# Voyage exists here to answer the one question Cloudflare cannot - whether a
# bad result is about RERANKING or about one cheap 2023-era base model.
RERANKERS = {"cloudflare": CLOUDFLARE_RERANK, "voyage": VOYAGE_RERANK}
RERANKER = CLOUDFLARE_RERANK  # main() replaces this from the command line
WINDOWS = (1, 5, 10, 20, 50)

# Seconds to wait between calls, because the provider raises on a 429 rather
# than retrying and pacing is the caller's job - the same split score_hybrid
# already uses for the embedders' per-minute token budgets.
#
# MEASURED 2026-09-11, and it corrects CLAUDE.md. Voyage's Platform Accounts
# row claims "4M TPM / 2,000 RPM". A card-free account really gets 3 RPM and
# 10K TPM, and its own 429 says so.
#
# The binding limit is the TOKENS, not the request rate, and that took two
# tries to establish. One 50-document call is ~11,400 tokens, which on its own
# exceeds 10K TPM - it succeeds at 65s spacing because the bucket refills, and
# 429s at 21s spacing because three such calls are ~34K in a minute. So the
# real ceiling is roughly ONE 50-document call every 70 seconds, which makes
# Voyage unusable as a PER-QUERY reranker on the free tier: 30 claims would be
# 35 minutes of waiting. Recorded for slice 8, which owns the chain order.
PACE = {"rerank-2.5-lite": 75.0}

# Dense-margin thresholds for the gate. Cosine margins between the top two hits
# are small, so the grid is small; it is swept rather than chosen, because a
# threshold in this project is calibrated and never guessed.
GATE_GRID = (0.0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.10)

# Slice 5's named candidate: a SMALL k with a SMALL keyword weight is the only
# region that was never worse than vector alone on any run.
FUSION_K, FUSION_WEIGHT = 5, 0.15


def cached_vectors(corpus: str, model: str, what: str) -> list:
    path = EMBED_CACHE / f"{corpus}_{model}_{what}.pkl"
    if not path.exists():
        raise SystemExit(
            f"{path} is missing. Run score_hybrid.py for this corpus and "
            f"embedder first - it caches the embeddings this script reuses."
        )
    return pickle.loads(path.read_bytes())


def dense_orders(queries, query_vectors, chunk_vectors) -> dict[str, list]:
    """Cosine against every chunk. Vectors are already unit length, so the dot
    product IS the cosine - embed/ normalises before returning."""
    out = {}
    for query, asked in zip(queries, query_vectors, strict=True):
        scored = [
            (i, sum(a * b for a, b in zip(asked, stored, strict=True)))
            for i, stored in enumerate(chunk_vectors)
        ]
        out[query.id] = sorted(scored, key=lambda kv: (-kv[1], kv[0]))
    return out


class PairScores:
    """Rerank scores, cached per (query, chunk) pair.

    Per PAIR and not per call, because a cross-encoder is pointwise: it runs
    one forward pass per (query, document) and the other documents in the
    request do not change the answer. That is verified below rather than
    assumed - if a provider normalised across the set, this cache would be
    quietly wrong and every number after it would inherit the error.
    """

    def __init__(self, corpus: str) -> None:
        CACHE.mkdir(parents=True, exist_ok=True)
        self.path = CACHE / f"{corpus}_{RERANKER.model.replace('/', '_')}.json"
        self.scores: dict[str, float] = (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path.exists()
            else {}
        )
        self.calls = 0

    def key(self, query_id: str, chunk_index: int) -> str:
        return f"{query_id}:{chunk_index}"

    def fetch(self, query, chunk_indexes: list[int], documents: list[str]) -> None:
        missing = [i for i in chunk_indexes if self.key(query.id, i) not in self.scores]
        if not missing:
            return
        for start in range(0, len(missing), SEARCH_LIMIT):
            batch = missing[start : start + SEARCH_LIMIT]
            if wait := PACE.get(RERANKER.model, 0.0):
                time.sleep(wait)
            ranking = RERANKER.rank(query.text, [documents[i] for i in batch])
            self.calls += 1
            for place, score in zip(ranking.order, ranking.scores, strict=True):
                self.scores[self.key(query.id, batch[place])] = score
        self.path.write_text(json.dumps(self.scores), encoding="utf-8")

    def order(self, query_id: str, chunk_indexes: list[int]) -> list[int]:
        return sorted(
            chunk_indexes,
            key=lambda i: (-self.scores[self.key(query_id, i)], i),
        )


def verify_pointwise(query, documents: list[str], candidates: list[int]) -> None:
    """Score one pair inside two different sets and compare.

    Costs 2 calls and protects every number in this file. The identical-vectors
    bug in slice 4 produced confident, publishable-looking numbers from a
    broken fixture; this is the same class of check, run before the fixture is
    trusted rather than after.
    """
    probe = candidates[0]
    wait = PACE.get(RERANKER.model, 0.0)
    small = RERANKER.rank(query.text, [documents[probe], documents[candidates[1]]])
    time.sleep(wait)
    wide = RERANKER.rank(query.text, [documents[i] for i in candidates[:10]])
    time.sleep(wait)

    in_small = small.scores[small.order.index(0)]
    in_wide = wide.scores[wide.order.index(0)]
    drift = abs(in_small - in_wide)

    print(
        f"  pointwise check: chunk {probe} scored {in_small:.6f} among 2 docs "
        f"and {in_wide:.6f} among 10 -> drift {drift:.2e}"
    )
    if drift > 1e-6:
        raise SystemExit(
            "the score MOVED with the rest of the batch, so this reranker is "
            "not pointwise and the per-pair cache would be wrong. Cache per "
            "CALL instead, and re-run everything."
        )


def place_of(order: list[int], wanted: set[int], n: int) -> int:
    for place, i in enumerate(order, 1):
        if i in wanted:
            return place
    return n + 1


def metrics(places: list[int], n: int) -> dict[str, float]:
    total = len(places)
    out = {f"r@{k}": sum(1 for p in places if p <= k) / total for k in WINDOWS}
    out["MRR"] = sum(1 / p for p in places if p <= n) / total
    return out


def row(label: str, m: dict[str, float]) -> str:
    cells = " ".join(f"{m[f'r@{k}']:6.3f}" for k in WINDOWS)
    return f"  {label:34} {cells} {m['MRR']:7.3f}"


def header() -> str:
    cells = " ".join(f"{'r@' + str(k):>6}" for k in WINDOWS)
    return f"\n  {'strategy':34} {cells} {'MRR':>7}"


def main() -> int:
    load_dotenv(".env")
    if len(sys.argv) < 3 or sys.argv[1] not in CORPORA or sys.argv[2] not in EMBEDDERS:
        print(
            f"usage: {sys.argv[0]} {{{'|'.join(CORPORA)}}} "
            f"{{{'|'.join(EMBEDDERS)}}} [--fusion]",
            file=sys.stderr,
        )
        return 2

    global RERANKER
    corpus, embedder = sys.argv[1], EMBEDDERS[sys.argv[2]]
    want_fusion = "--fusion" in sys.argv
    for name, candidate in RERANKERS.items():
        if f"--{name}" in sys.argv:
            RERANKER = candidate

    chunks, queries = CORPORA[corpus]()
    n = len(chunks)
    documents = [c.embed_text for c in chunks]
    window = min(SEARCH_LIMIT, n)

    print(
        f"\n{corpus}: {n} chunks, {len(queries)} queries, {embedder.model}, "
        f"reranked by {RERANKER.model}"
    )
    print(
        f"  the top-{window} window is {window / n:.0%} of this corpus - at a real "
        f"10,000-chunk artifact it would be {window / 10_000:.1%}"
    )

    chunk_vectors = cached_vectors(corpus, embedder.model, "chunks")
    query_vectors = cached_vectors(corpus, embedder.model, "queries")
    dense = dense_orders(queries, query_vectors, chunk_vectors)

    pairs = PairScores(corpus)
    verify_pointwise(queries[0], documents, [i for i, _ in dense[queries[0].id][:10]])

    # --- candidate sets -----------------------------------------------------
    vector_candidates = {q.id: [i for i, _ in dense[q.id][:window]] for q in queries}

    fused_candidates: dict[str, list[int]] = {}
    if want_fusion:
        pg, counts, terms, matched = keyword_signals(chunks, queries)
        sparse = bm25(counts, terms, n)
        for q in queries:
            order = rrf(
                [
                    [i for i, _ in dense[q.id]],
                    [i for i, _ in sparse[q.id]],
                ],
                FUSION_K,
                [1.0, FUSION_WEIGHT],
            )
            fused_candidates[q.id] = order[:window]

    # --- pay for the rerank scores -----------------------------------------
    for q in queries:
        needed = set(vector_candidates[q.id]) | set(fused_candidates.get(q.id, []))
        pairs.fetch(q, sorted(needed), documents)
    print(f"  rerank calls spent this run: {pairs.calls}")

    truth = {q.id: targets(chunks, q) for q in queries}
    results: dict[str, dict[str, float]] = {}

    def score(label: str, orders: dict[str, list[int]]) -> None:
        results[label] = metrics(
            [place_of(orders[q.id], truth[q.id], n) for q in queries], n
        )

    # --- MEASUREMENT 1: does reranking help at all --------------------------
    score("vector alone", {q.id: [i for i, _ in dense[q.id]] for q in queries})
    reranked = {q.id: pairs.order(q.id, vector_candidates[q.id]) for q in queries}
    score("vector -> rerank", reranked)

    # --- MEASUREMENT 4: does slice 5's fusion gain survive reranking --------
    if want_fusion:
        score("wRRF alone", {q.id: fused_candidates[q.id] for q in queries})
        score(
            f"wRRF k={FUSION_K} w={FUSION_WEIGHT} -> rerank",
            {q.id: pairs.order(q.id, fused_candidates[q.id]) for q in queries},
        )

    # --- MEASUREMENT 3: is the gate worth having ---------------------------
    margins = {q.id: margin([s for _, s in dense[q.id][:window]]) for q in queries}
    gated: dict[float, dict[str, float]] = {}
    skipped_at: dict[float, int] = {}
    for tau in GATE_GRID:
        orders = {}
        skips = 0
        for q in queries:
            if margins[q.id] > tau:
                orders[q.id] = vector_candidates[q.id]
                skips += 1
            else:
                orders[q.id] = reranked[q.id]
        gated[tau] = metrics(
            [place_of(orders[q.id], truth[q.id], n) for q in queries], n
        )
        skipped_at[tau] = skips

    # --- report -------------------------------------------------------------
    print(header())
    for label, m in results.items():
        print(row(label, m))

    before, after = results["vector alone"], results["vector -> rerank"]
    ceiling = before[f"r@{window}"] if window in WINDOWS else before["r@50"]
    print("\n  MEASUREMENT 1 - does reranking help")
    print(f"    r@10 {before['r@10']:.3f} -> {after['r@10']:.3f}")
    print(f"    MRR  {before['MRR']:.3f} -> {after['MRR']:.3f}")
    headroom = ceiling - before["r@10"]
    if headroom > 0:
        captured = (after["r@10"] - before["r@10"]) / headroom
        print(
            f"    headroom was {headroom:.3f} (r@{window} {ceiling:.3f} minus "
            f"r@10 {before['r@10']:.3f}); captured {captured:+.0%} of it"
        )
    else:
        print(
            f"    NO HEADROOM AT r@10: r@{window} and r@10 are both "
            f"{ceiling:.3f}, so this corpus cannot show a gain here"
        )
    same = before[f"r@{window}"] == after[f"r@{window}"] if window in WINDOWS else None
    print(
        f"    sanity: r@{window} unchanged? {same} "
        f"(a reranker only REORDERS what it was given - if this is False the "
        f"measurement is broken, not the reranker)"
    )
    print(
        f"    the r@1 / MRR question: r@1 is {before['r@1']:.3f} and MRR is "
        f"{before['MRR']:.3f} for vector alone - they are NOT the same number"
    )

    print("\n  MEASUREMENT 2 - how many chunks to send")
    print(f"    {'window':>8}  {'before':>7}  {'after':>7}  {'delta':>7}")
    for k in WINDOWS:
        d = after[f"r@{k}"] - before[f"r@{k}"]
        print(
            f"    {('top-' + str(k)):>8}  {before[f'r@{k}']:7.3f}  "
            f"{after[f'r@{k}']:7.3f}  {d:+7.3f}"
        )

    print("\n  MEASUREMENT 3 - is the skip gate worth having")
    print(
        f"    dense margin: median {statistics.median(margins.values()):.4f}, "
        f"min {min(margins.values()):.4f}, max {max(margins.values()):.4f}"
    )
    print(f"    {'tau':>7}  {'skipped':>9}  {'r@10':>6}  {'MRR':>7}")
    for tau in GATE_GRID:
        print(
            f"    {tau:7.3f}  {skipped_at[tau]:4d}/{len(queries):<4}  "
            f"{gated[tau]['r@10']:6.3f}  {gated[tau]['MRR']:7.3f}"
        )
    print(
        f"    always rerank (tau = none): r@10 {after['r@10']:.3f}, "
        f"MRR {after['MRR']:.3f}"
    )

    print("\n  BY QUESTION TYPE - where reranking loses, and whether it has a pattern")
    print(f"    {'asks':11} {'n':>3}  {'before':>7}  {'after':>7}  {'delta':>7}")
    kinds: dict[str, list] = {}
    for q in queries:
        kinds.setdefault(q.asks, []).append(q)
    for asks in sorted(kinds):
        group = kinds[asks]
        was = statistics.mean(
            1 / place_of([i for i, _ in dense[q.id]], truth[q.id], n) for q in group
        )
        now = statistics.mean(
            1 / place_of(reranked[q.id], truth[q.id], n) for q in group
        )
        print(
            f"    {asks:11} {len(group):3d}  {was:7.3f}  {now:7.3f}  {now - was:+7.3f}"
        )

    if want_fusion:
        print("\n  MEASUREMENT 4 - does slice 5's fusion gain survive reranking")
        base = results["vector -> rerank"]
        mix = results[f"wRRF k={FUSION_K} w={FUSION_WEIGHT} -> rerank"]
        for k in ("r@5", "r@10", "MRR"):
            print(f"    {k:5} {base[k]:.3f} -> {mix[k]:.3f}  ({mix[k] - base[k]:+.3f})")

    if "DATABASE_URL" not in os.environ and want_fusion:
        print("\n  (--fusion needs DATABASE_URL for the BM25 channel)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
