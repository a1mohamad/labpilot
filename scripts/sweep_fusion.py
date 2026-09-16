"""Fine-tune wRRF, and measure how the answer moves with CORPUS SIZE.

Two things slice 8's first pass skipped.

**wRRF was never tuned.** It won - better or equal on all six runs, worse on
nothing - and then shipped at `k=5 w=0.15`, the setting slice 5 picked for
being SAFE on two saturated corpora. Safe means "keyword channel almost
switched off", which is why it could not hurt and also why it under-delivers
where there is something to win: on geo, `k=30 w=0.3` is three times better
at `r@50`. A winner earns a real grid.

**Size was varied by accident, not by design.** The corpora happened to be
82, 335 and 729 chunks. That confounds size with language and domain - geo is
the biggest AND the only Go AND the only unsaturated one, so "the gain
appears on geo" and "the gain appears on big corpora" cannot be told apart.
The ladder fixes that: ONE corpus, sliced to several sizes, everything else
held still.

    PYTHONPATH=. python scripts/sweep_fusion.py geo codestral --ladder
    PYTHONPATH=. python scripts/sweep_fusion.py requests codestral --grid

Both are FREE - embeddings and Postgres lexemes come from cache, and the
sweep is arithmetic.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from scripts.score_hybrid import (
    CORPORA,
    EMBEDDERS,
    bm25,
    embedded,
    keyword_signals,
    metrics,
    place_of,
    rrf,
    targets,
)

# A REAL grid this time. Slice 5 swept k in {5,10,20,30,60} and w up to 1.0
# but judged every setting on corpora where r@50 was already 1.000, so the
# only settings that could not lose were the ones that barely did anything.
K_GRID = (5, 10, 20, 30, 45, 60, 90)
W_GRID = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.7)

# The sizes a user actually sends. CLAUDE.md's own ladder-of-decisions talks
# about 1,000-10,000 chunk repositories, but most uploads are a handful of
# files, so the interesting range is BELOW 1,000 and the top of it is the
# exception rather than the target.
LADDER = (100, 200, 300, 400, 600, 800, 1000)


def evaluate(chunks, queries, dense, sparse_scores, n, k, w) -> dict:
    """One fusion setting, scored over every query."""
    got = []
    for q in queries:
        want = targets(chunks, q)
        d = [i for i, _ in dense[q.id]]
        s = [i for i, _ in sparse_scores.get(q.id, [])]
        order = rrf([d, s], k, [1.0, w]) if s else d
        got.append(place_of(order, want, n))
    return metrics(got, n)


def subset(chunks, vectors, queries, size: int):
    """The first `size` chunks, and the queries whose answer is still in them.

    Truncating the corpus and KEEPING every query would silently turn a size
    study into a study of how many answers were deleted - recall would fall
    for a reason that has nothing to do with retrieval.
    """
    kept_chunks = chunks[:size]
    kept_vectors = vectors[:size]
    kept = [q for q in queries if targets(kept_chunks, q)]
    return kept_chunks, kept_vectors, kept


def main() -> int:
    load_dotenv(".env")
    if len(sys.argv) < 3:
        raise SystemExit(f"usage: {sys.argv[0]} <corpus> <embedder> [--grid|--ladder]")
    name, embedder = sys.argv[1], EMBEDDERS[sys.argv[2]]
    chunks, queries = CORPORA[name]()

    vectors = embedded(
        embedder,
        [c.embed_text for c in chunks],
        task="document",
        tag=f"{name}_{embedder.model}_chunks",
    )
    q_vectors = embedded(
        embedder,
        [q.text for q in queries],
        task="query",
        tag=f"{name}_{embedder.model}_queries",
    )

    if "--ladder" in sys.argv:
        print(f"{name} / {embedder.model} - SIZE LADDER, one corpus, sliced\n")
        print(
            f"{'chunks':>7}{'queries':>9}{'r@10':>8}{'r@50':>8}{'MRR':>8}"
            f"{'  |  wRRF best':<16}{'r@50':>8}{'MRR':>8}"
        )
        for size in LADDER:
            if size > len(chunks):
                continue
            sub_c, sub_v, sub_q = subset(chunks, vectors, queries, size)
            if len(sub_q) < 8:
                continue
            sub_qv = [q_vectors[queries.index(q)] for q in sub_q]
            dense = dense_orders(sub_q, sub_qv, sub_v)
            sparse = sparse_for(name, sub_c, sub_q, size)
            base = evaluate(sub_c, sub_q, dense, sparse, size, 60, 0.0)
            best, best_cfg = None, None
            for k in K_GRID:
                for w in W_GRID:
                    m = evaluate(sub_c, sub_q, dense, sparse, size, k, w)
                    if best is None or (m["r@50"], m["MRR"]) > (
                        best["r@50"],
                        best["MRR"],
                    ):
                        best, best_cfg = m, (k, w)
            print(
                f"{size:>7}{len(sub_q):>9}{base['r@10']:>8.3f}{base['r@50']:>8.3f}"
                f"{base['MRR']:>8.3f}  |  k={best_cfg[0]:<3} w={best_cfg[1]:<5}"
                f"{best['r@50']:>8.3f}{best['MRR']:>8.3f}",
                flush=True,
            )
        return 0

    n = len(chunks)
    dense = dense_orders(queries, q_vectors, vectors)
    sparse = sparse_for(name, chunks, queries, n)
    base = evaluate(chunks, queries, dense, sparse, n, 60, 0.0)
    print(f"{name} / {embedder.model} - wRRF GRID, {n} chunks, {len(queries)} queries")
    print(
        f"  vector alone   r@5 {base['r@5']:.3f}  r@10 {base['r@10']:.3f}  "
        f"r@50 {base['r@50']:.3f}  MRR {base['MRR']:.3f}\n"
    )
    rows = []
    for k in K_GRID:
        for w in W_GRID:
            m = evaluate(chunks, queries, dense, sparse, n, k, w)
            rows.append((k, w, m))
    rows.sort(key=lambda r: (-r[2]["r@50"], -r[2]["MRR"]))
    print(f"{'k':>4}{'w':>7}{'r@5':>8}{'r@10':>8}{'r@50':>8}{'MRR':>8}   vs vector")
    for k, w, m in rows[:14]:
        print(
            f"{k:>4}{w:>7}{m['r@5']:>8.3f}{m['r@10']:>8.3f}{m['r@50']:>8.3f}"
            f"{m['MRR']:>8.3f}   r@50 {m['r@50'] - base['r@50']:+.3f} "
            f"MRR {m['MRR'] - base['MRR']:+.3f}"
        )
    worst = min(rows, key=lambda r: (r[2]["r@50"], r[2]["MRR"]))
    print(
        f"\n  worst setting: k={worst[0]} w={worst[1]}  "
        f"r@50 {worst[2]['r@50'] - base['r@50']:+.3f} "
        f"MRR {worst[2]['MRR'] - base['MRR']:+.3f}"
    )
    never_worse = [
        (k, w)
        for k, w, m in rows
        if m["r@50"] >= base["r@50"] and m["MRR"] >= base["MRR"]
    ]
    print(
        f"  settings never worse than vector on BOTH r@50 and MRR: {len(never_worse)}"
    )
    return 0


def dense_orders(queries, query_vectors, chunk_vectors) -> dict:
    out = {}
    for query, asked in zip(queries, query_vectors, strict=True):
        scored = [
            (i, sum(a * b for a, b in zip(asked, stored, strict=True)))
            for i, stored in enumerate(chunk_vectors)
        ]
        out[query.id] = sorted(scored, key=lambda kv: (-kv[1], kv[0]))
    return out


def sparse_for(name: str, chunks, queries, n: int) -> dict:
    """BM25 over Postgres's own lexemes, or nothing when the database is out.

    A run without the keyword channel still measures the size ladder's
    vector half, so a missing DATABASE_URL degrades the study rather than
    ending it.
    """
    try:
        _, counts, terms, _ = keyword_signals(chunks, queries)
        return bm25(counts, terms, n)
    except Exception as exc:  # noqa: BLE001 - the database is optional here
        print(f"  (no keyword channel: {str(exc)[:60]})")
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
