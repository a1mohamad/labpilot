"""Score vector search, keyword search, BM25 and every fusion of them.

CLAUDE.md's rule is that a measurement you cannot repeat is a number, not a
result -- which is why score_retrieval.py is in the repository. This is the
same instrument for slice 5, and it answers a bigger question: not "is the
embedder good" but "does adding a keyword channel help at all".

    PYTHONPATH=. python scripts/score_hybrid.py quora codestral
    PYTHONPATH=. python scripts/score_hybrid.py requests codestral --sweep
    PYTHONPATH=. python scripts/score_hybrid.py quora codestral --sweep-bm25

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

# BM25's two knobs. These are the TEXTBOOK values and, unlike RRF's k and
# weight, they were never swept -- the 2026-09-07 run varied only the fusion's
# k and weight, so two of the four hyperparameters were held at a guess. And
# the textbook has already been wrong here once: RRF's own k=60 w=1.0 is the
# worst row in our table. --sweep-bm25 is what closes that gap.
K1, B = 1.2, 0.75

# A small, principled grid rather than a dense one. `b` normalises by document
# length, and our chunks are capped near 510 tokens and fairly uniform, so it
# has far less to bite on than in a corpus of mixed lengths -- expect it to be
# nearly flat. `k1` is saturation, which should matter more on code, where one
# identifier repeats many times.
BM25_GRID = (
    (1.2, 0.75),
    (0.9, 0.75),
    (1.6, 0.75),
    (2.0, 0.75),
    (1.2, 0.30),
    (1.2, 0.00),
)

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


def bm25(
    counts, terms, n_chunks: int, *, k1: float = K1, b: float = B
) -> dict[str, list[tuple[int, float]]]:
    """BM25 by hand, returning SCORES and not only an order.

    Postgres cannot do this: ts_rank(tsvector, tsquery) is handed ONE
    document, so it cannot know document frequency and has no IDF at all.
    The scores are kept because score fusion and CombMNZ need magnitudes,
    where RRF and RESCUE need only places.
    """
    lengths = {i: sum(counts.get(i, {}).values()) for i in range(n_chunks)}
    average = statistics.mean(lengths.values()) if lengths else 1.0
    seen: dict[str, int] = defaultdict(int)
    for i in range(n_chunks):
        for lexeme in counts.get(i, {}):
            seen[lexeme] += 1

    def scored(query_terms: list[str]) -> list[tuple[int, float]]:
        scores = {}
        for i in range(n_chunks):
            doc, total = counts.get(i, {}), 0.0
            for t in query_terms:
                f = doc.get(t, 0)
                if not f:
                    continue
                idf = math.log((n_chunks - seen[t] + 0.5) / (seen[t] + 0.5) + 1.0)
                norm = k1 * (1 - b + b * lengths[i] / average)
                total += idf * (f * (k1 + 1)) / (f + norm)
            if total > 0:
                scores[i] = total
        return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))

    return {qid: scored(t) for qid, t in terms.items()}


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


def places(scored: list[tuple[int, float]]) -> list[int]:
    """Throw the scores away and keep the order. RRF and RESCUE want places."""
    return [i for i, _ in scored]


def minmax(scored: list[tuple[int, float]]) -> dict[int, float]:
    """Rescale one ranker's scores to [0, 1].

    This is the step RRF exists to AVOID: a cosine similarity and a BM25 score
    are on different scales, so they cannot be added until both are rescaled,
    and the rescaling is then one more thing that can be wrong.
    """
    if not scored:
        return {}
    values = [s for _, s in scored]
    low, high = min(values), max(values)
    if high == low:
        return {i: 1.0 for i, _ in scored}
    return {i: (s - low) / (high - low) for i, s in scored}


def score_fusion(dense, sparse, alpha: float) -> list[int]:
    """Add the normalised scores. Standard, not ours.

    Best average MRR of anything measured (0.671 at alpha=0.85) and it still
    lost recall@50 on a single run, with no mechanism to explain the win. One
    average is not evidence.
    """
    d, s = minmax(dense), minmax(sparse)
    total = {
        i: alpha * d.get(i, 0.0) + (1 - alpha) * s.get(i, 0.0) for i in set(d) | set(s)
    }
    return [i for i, _ in sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))]


def combmnz(dense, sparse) -> list[int]:
    """Sum the normalised scores, then multiply by how many rankers found it.

    Standard, not ours. It is the exact OPPOSITE bet to RESCUE: it rewards
    agreement hard, where RESCUE refuses to punish disagreement at all.
    """
    d, s = minmax(dense), minmax(sparse)
    total = {}
    for i in set(d) | set(s):
        found_by = (i in d) + (i in s)
        total[i] = (d.get(i, 0.0) + s.get(i, 0.0)) * found_by
    return [i for i, _ in sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))]


def adaptive_rrf(dense, sparse, k: int, n_chunks: int, hits: int) -> list[int]:
    """Weight the keyword list by how SELECTIVE it was on THIS query.

    Ours, invented 2026-09-06. The observation behind it is real: for quora D2
    the keyword query matched 7 of 82 chunks and was right, and for D6 it
    matched 73 of 82 and was noise. Selectivity costs nothing to compute.

    It won on quora (best MRR, 0.730) and was middling on requests, so it is
    NOT a candidate. It is here so the reported number stays reproducible.
    """
    weight = 1.0 - (hits / n_chunks if n_chunks else 0.0)
    return rrf([places(dense), places(sparse)], k, [1.0, weight])


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
    """label -> (dense_scored, sparse_scored, n_chunks, hits) -> order

    The WINNERS are built first and always: vector alone is what ships today,
    and wRRF and RESCUE are the two named candidates for slice 8. The three
    after them are here so their reported numbers stay reproducible, NOT
    because they are contenders.

    The rule that separates the two groups: judge a method by how many
    independent ways it was shown better, never by its best single number.
    """
    built = {
        "vector": lambda d, s, n, hits: places(d),
        "bm25": lambda d, s, n, hits: places(s),
    }
    weights = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.5, 1.0) if sweep else (0.15,)
    ks = (5, 10, 20, 30, 60) if sweep else (5,)
    for k in ks:
        for w in weights:
            built[f"wRRF k={k:<2} w={w}"] = lambda d, s, n, hits, k=k, w=w: rrf(
                [places(d), places(s)], k, [1.0, w]
            )
    pairs = ((3, 20), (5, 5), (5, 20), (10, 10)) if sweep else ((5, 20),)
    for m, after in pairs:
        built[f"RESCUE m={m} after={after}"] = lambda d, s, n, hits, m=m, a=after: (
            rescue(places(d), places(s), m, a)
        )

    # Also-rans, restored 2026-09-07. CLAUDE.md reported numbers for all three
    # and the committed script implemented NONE of them - they lived in a
    # session scratchpad and were lost, exactly as score_retrieval.py was lost
    # before it was committed. A measurement you cannot repeat is a number.
    for alpha in (0.7, 0.85, 0.95) if sweep else (0.85,):
        built[f"score a={alpha}"] = lambda d, s, n, hits, a=alpha: score_fusion(d, s, a)
    built["CombMNZ"] = lambda d, s, n, hits: combmnz(d, s)
    for k in (5, 10, 60) if sweep else (10,):
        built[f"ADAPTIVE k={k}"] = lambda d, s, n, hits, k=k: adaptive_rrf(
            d, s, k, n, hits
        )
    return built


def evaluate(chunks, queries, dense_by_q, sparse_by_q, matched, pg, n, sweep):
    built = rankers(sweep)
    built["ts_rank"] = None  # filled below, it needs its own order per query
    results = {}
    for label, fn in built.items():
        found = []
        for q in queries:
            order = (
                pg["ts_rank"][q.id]
                if fn is None
                else fn(dense_by_q[q.id], sparse_by_q[q.id], n, matched[q.id])
            )
            found.append(place_of(order, targets(chunks, q), n))
        results[label] = metrics(found, n)
    return results


def report(results) -> None:
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


def main() -> int:
    load_dotenv(".env")
    if len(sys.argv) < 3 or sys.argv[1] not in CORPORA:
        print(
            f"usage: {sys.argv[0]} {{{'|'.join(CORPORA)}}} "
            f"{{{'|'.join(EMBEDDERS)}}} [--sweep] [--sweep-bm25]",
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

    n = len(chunks)
    dense_by_q = {}
    for q, qv in zip(queries, asked, strict=True):
        dense_by_q[q.id] = sorted(
            (
                (i, sum(a * b for a, b in zip(qv, vectors[i], strict=True)))
                for i in range(n)
            ),
            key=lambda kv: (-kv[1], kv[0]),
        )

    # The fourth and fifth hyperparameters. Held at the textbook guess unless
    # --sweep-bm25 says otherwise, because the 2026-09-07 run never varied them.
    grid = BM25_GRID if "--sweep-bm25" in sys.argv else ((K1, B),)
    for k1, b in grid:
        if len(grid) > 1:
            print(f"\n### BM25 k1={k1} b={b}")
        sparse_by_q = bm25(counts, terms, n, k1=k1, b=b)
        report(
            evaluate(chunks, queries, dense_by_q, sparse_by_q, matched, pg, n, sweep)
        )

    print(
        f"\n  keyword matched, median: "
        f"{statistics.median(matched.values()):.0f} of {n} chunks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
