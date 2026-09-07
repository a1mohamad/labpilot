"""Score vector search, keyword search, BM25 and every fusion of them.

CLAUDE.md's rule is that a measurement you cannot repeat is a number, not a
result -- which is why score_retrieval.py is in the repository. This is the
same instrument for slice 5, and it answers a bigger question: not "is the
embedder good" but "does adding a keyword channel help at all".

    PYTHONPATH=. python scripts/score_hybrid.py quora codestral
    PYTHONPATH=. python scripts/score_hybrid.py requests codestral --sweep

The `requests` corpus is third-party source and is deliberately NOT committed.
Fetch it first, at the commit the query file names:

    git clone --depth 1 https://github.com/psf/requests <dir>
    set LABPILOT_REQUESTS_SRC=<dir>/src/requests

Embeddings are cached under .cache/, so only the first run spends quota.
Keyword ranking needs DATABASE_URL: it uses Postgres full-text search, and
BM25 reads the SAME tokens, so the ranking formula is the only difference.
"""

from __future__ import annotations

import json
import math
import os
import pickle
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from labpilot.embed import CODESTRAL_EMBED, GEMINI_EMBEDDING, embed_batches
from labpilot.ingest import chunk_file
from labpilot.tokens import estimate_tokens

SAMPLES = Path("data/samples")
CACHE = Path(".cache/hybrid")
EMBEDDERS = {"codestral": CODESTRAL_EMBED, "google": GEMINI_EMBEDDING}

# Each provider publishes a per-minute token budget, and the embedder raises on
# a 429 rather than retrying, so pacing is the caller's job.
TOKENS_PER_MINUTE = {"codestral-embed": 50_000, "gemini-embedding-001": 30_000}

K1, B = 1.2, 0.75

# Turning the query into an OR of its lexemes is not a detail. plainto_tsquery
# joins with AND, and one 500-token chunk almost never holds every word of a
# sentence: measured 2026-09-06, AND scored recall@5 of 0.000 on all 17 quora
# queries while OR scored 0.824. The operator matters more than the ranker.
OR_QUERY = """
    to_tsquery('english',
        array_to_string(tsvector_to_array(to_tsvector('english', %s)), ' | '))
"""


@dataclass(frozen=True)
class Query:
    id: str
    text: str
    file: str
    expects: tuple[int, ...]
    asks: str
    wording: str


def load_quora() -> tuple[list, list[Query]]:
    chunks = list(
        chunk_file(SAMPLES / "quora_siamese" / "B_train.py", side="B", artifact_id="q")
    )
    raw = json.loads(
        (SAMPLES / "quora_siamese" / "queries.json").read_text(encoding="utf-8")
    )
    queries = [
        Query(q["id"], q["query"], "B_train.py", tuple(q["expects"]), q["kind"], "n/a")
        for q in raw
    ]
    return chunks, queries


def load_requests() -> tuple[list, list[Query]]:
    src = os.environ.get("LABPILOT_REQUESTS_SRC", "").strip()
    if not src or not Path(src).is_dir():
        raise SystemExit(
            "LABPILOT_REQUESTS_SRC is not set to a directory. This corpus is "
            "third-party source and is not committed; see the module docstring."
        )
    chunks = []
    for path in sorted(Path(src).glob("*.py")):
        chunks.extend(
            chunk_file(path, side="B", artifact_id="requests", source=path.name)
        )
    raw = json.loads(
        (SAMPLES / "requests_http" / "queries.json").read_text(encoding="utf-8")
    )
    queries = [
        Query(
            q["id"], q["query"], q["file"], tuple(q["expects"]), q["asks"], q["wording"]
        )
        for q in raw["queries"]
    ]
    return chunks, queries


CORPORA = {"quora": load_quora, "requests": load_requests}


def targets(chunks, query: Query) -> set[int]:
    """Chunks holding an answer line. The file must match: a repository has
    many files, and line 186 exists in nearly all of them."""
    return {
        i
        for i, c in enumerate(chunks)
        if c.source == query.file
        and any(c.start_line <= line <= c.end_line for line in query.expects)
    }


def embedded(embedder, texts: list[str], *, task: str, tag: str) -> list:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{tag}.pkl"
    if cached.exists():
        return pickle.loads(cached.read_bytes())

    budget = TOKENS_PER_MINUTE[embedder.model]
    vectors: list = []
    spent, window = 0, time.time()
    for start in range(0, len(texts), 96):
        batch = texts[start : start + 96]
        cost = sum(estimate_tokens(t) for t in batch)
        if spent + cost > budget * 0.85:
            time.sleep(max(0.0, 62 - (time.time() - window)))
            spent, window = 0, time.time()
        for out in embed_batches(embedder, batch, task=task, size=len(batch)):
            vectors.extend(out.vectors)
        spent += cost
        print(f"    {len(vectors)}/{len(texts)}", flush=True)

    cached.write_bytes(pickle.dumps(vectors))
    return vectors


def keyword_signals(chunks, queries):
    """Postgres orders, and the per-chunk term counts BM25 needs."""
    orders: dict[str, dict[str, list[int]]] = {"ts_rank": {}, "ts_rank_cd": {}}
    matched: dict[str, int] = {}
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=15) as conn:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("create temp table bench (i int primary key, txt text)")
        cur.executemany(
            "insert into bench values (%s, %s)",
            [(i, c.embed_text) for i, c in enumerate(chunks)],
        )
        cur.execute(
            "select b.i, u.lexeme, coalesce(array_length(u.positions, 1), 1) "
            "from bench b, unnest(to_tsvector('english', b.txt)) u"
        )
        counts: dict[int, dict[str, int]] = defaultdict(dict)
        for i, lexeme, n in cur.fetchall():
            counts[i][lexeme] = n

        terms = {}
        for q in queries:
            cur.execute(
                "select lexeme from unnest(to_tsvector('english', %s))", (q.text,)
            )
            terms[q.id] = [row[0] for row in cur.fetchall()]

        for fn in ("ts_rank", "ts_rank_cd"):
            for q in queries:
                cur.execute(
                    f"select i, {fn}(to_tsvector('english', txt), q) as r "
                    f"from bench, {OR_QUERY} as q "
                    f"where to_tsvector('english', txt) @@ q order by r desc, i",
                    (q.text,),
                )
                rows = cur.fetchall()
                orders[fn][q.id] = [i for i, _ in rows]
                matched[q.id] = len(rows)
    return orders, counts, terms, matched


def bm25(counts, terms, n_chunks: int) -> dict[str, list[int]]:
    """BM25 by hand. Postgres cannot do this: ts_rank(tsvector, tsquery) is
    handed ONE document, so it cannot know document frequency and has no IDF.
    """
    lengths = {i: sum(counts.get(i, {}).values()) for i in range(n_chunks)}
    average = statistics.mean(lengths.values()) if lengths else 1.0
    seen: dict[str, int] = defaultdict(int)
    for i in range(n_chunks):
        for lexeme in counts.get(i, {}):
            seen[lexeme] += 1

    def order(query_terms: list[str]) -> list[int]:
        scores = {}
        for i in range(n_chunks):
            doc, total = counts.get(i, {}), 0.0
            for t in query_terms:
                f = doc.get(t, 0)
                if not f:
                    continue
                idf = math.log((n_chunks - seen[t] + 0.5) / (seen[t] + 0.5) + 1.0)
                norm = K1 * (1 - B + B * lengths[i] / average)
                total += idf * (f * (K1 + 1)) / (f + norm)
            if total > 0:
                scores[i] = total
        return [i for i, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]

    return {qid: order(t) for qid, t in terms.items()}


def rrf(orders: list[list[int]], k: int, weights: list[float]) -> list[int]:
    score: dict[int, float] = defaultdict(float)
    for order, weight in zip(orders, weights, strict=True):
        for place, item in enumerate(order, 1):
            score[item] += weight / (k + place)
    return [i for i, _ in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))]


def rescue(dense: list[int], sparse: list[int], m: int, after: int) -> list[int]:
    """Keyword search may PROMOTE, never DEMOTE.

    RRF punishes a chunk only one list found. Measured on quora: D14 sat at
    place 5 under vector alone, BM25 never returned it, and RRF pushed it to 27
    because rival chunks collected points from both lists. Here the vector
    order is untouched above `after`, so recall@1..after cannot fall.
    """
    head = dense[:after]
    lifted = [i for i in sparse[:m] if i not in head]
    seen = set(head) | set(lifted)
    return head + lifted + [i for i in dense[after:] if i not in seen]


def place_of(order: list[int], wanted: set[int], n_chunks: int) -> int:
    for place, i in enumerate(order, 1):
        if i in wanted:
            return place
    return n_chunks + 1


def metrics(places: list[int], n_chunks: int) -> dict[str, float]:
    n = len(places)
    return {
        "r@1": sum(1 for p in places if p <= 1) / n,
        "r@5": sum(1 for p in places if p <= 5) / n,
        "r@10": sum(1 for p in places if p <= 10) / n,
        "r@50": sum(1 for p in places if p <= 50) / n,
        "MRR": sum(1 / p for p in places if p <= n_chunks) / n,
        "mean": statistics.mean(places),
    }


def rankers(sweep: bool):
    """label -> (dense_order, bm25_order, n) -> order"""
    built = {
        "vector": lambda d, s, n: d,
        "bm25": lambda d, s, n: s,
    }
    weights = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.5, 1.0) if sweep else (0.15,)
    ks = (5, 10, 20, 30, 60) if sweep else (5,)
    for k in ks:
        for w in weights:
            built[f"wRRF k={k:<2} w={w}"] = lambda d, s, n, k=k, w=w: rrf(
                [d, s], k, [1.0, w]
            )
    pairs = ((3, 20), (5, 5), (5, 20), (10, 10)) if sweep else ((5, 20),)
    for m, after in pairs:
        built[f"RESCUE m={m} after={after}"] = lambda d, s, n, m=m, a=after: rescue(
            d, s, m, a
        )
    return built


def main() -> int:
    load_dotenv(".env")
    if len(sys.argv) < 3 or sys.argv[1] not in CORPORA:
        print(
            f"usage: {sys.argv[0]} {{{'|'.join(CORPORA)}}} "
            f"{{{'|'.join(EMBEDDERS)}}} [--sweep]",
            file=sys.stderr,
        )
        return 2
    name, embedder = sys.argv[1], EMBEDDERS[sys.argv[2]]
    sweep = "--sweep" in sys.argv

    chunks, queries = CORPORA[name]()
    print(f"{name}: {len(chunks)} chunks, {len(queries)} queries, {embedder.model}")

    tag = f"{name}_{embedder.model}"
    vectors = embedded(
        embedder, [c.embed_text for c in chunks], task="document", tag=f"{tag}_chunks"
    )
    asked = embedded(
        embedder, [q.text for q in queries], task="query", tag=f"{tag}_queries"
    )
    pg, counts, terms, matched = keyword_signals(chunks, queries)
    sparse = bm25(counts, terms, len(chunks))

    n = len(chunks)
    orders = {}
    for q, qv in zip(queries, asked, strict=True):
        dense = sorted(
            range(n),
            key=lambda i: -sum(a * b for a, b in zip(qv, vectors[i], strict=True)),
        )
        orders[q.id] = (dense, sparse[q.id])

    built = rankers(sweep)
    built["ts_rank"] = None  # filled below, it needs its own order per query
    results = {}
    for label, fn in built.items():
        places = []
        for q in queries:
            dense, sp = orders[q.id]
            order = pg["ts_rank"][q.id] if fn is None else fn(dense, sp, n)
            places.append(place_of(order, targets(chunks, q), n))
        results[label] = metrics(places, n)

    print(
        f"\n  {'ranker':26} {'r@1':>6} {'r@5':>6} {'r@10':>6} {'r@50':>6} "
        f"{'MRR':>7} {'mean':>7}"
    )
    for label, m in results.items():
        print(
            f"  {label:26} {m['r@1']:6.3f} {m['r@5']:6.3f} {m['r@10']:6.3f} "
            f"{m['r@50']:6.3f} {m['MRR']:7.3f} {m['mean']:7.1f}"
        )

    base = results["vector"]
    print("\n  vs vector (r@50 is the one that decides what the model sees):")
    for label, m in results.items():
        if label == "vector":
            continue
        deltas = " ".join(
            f"{k} {m[k] - base[k]:+.3f}" for k in ("r@50", "r@10", "r@5", "MRR")
        )
        print(f"  {label:26} {deltas}")

    print(
        f"\n  keyword matched, median: "
        f"{statistics.median(matched.values()):.0f} of {n} chunks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
