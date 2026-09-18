"""Exact search against HNSW, on REAL artifacts, on the REAL instance.

Slice 8 job 3. The 2026-09-05 decision shipped exact search and named the one
condition that could overturn it: **time**, measured on real artifacts inside
the full system. Not recall - exact is 1.00 by definition. Not storage - exact
is 2.5x cheaper. Only time.

    PYTHONPATH=. python scripts/bench_index.py

Three things this run does that the earlier ones did not.

  IT USES SUPABASE, not a local container. Every latency in CLAUDE.md's
  1k-10k range came from a local pgvector image, and the one free-tier number
  - 10,019 ms at 30,000 rows - was 70x its local twin, because 500 MB of RAM
  stops holding the vectors and every query goes to disk.

  IT SEPARATES THE NETWORK FROM THE DATABASE. Client-observed latency here is
  ~275 ms and FLAT from 335 to 1,387 rows, because a round trip from this VPN
  exit to Frankfurt swamps the scan. Only EXPLAIN ANALYZE can compare exact
  against HNSW; the client number answers a different question.

  IT ASSERTS THE PLAN. Writing the ORDER BY the natural way silently falls
  back to a sort: same answers, no error, no warning. A row claiming to be an
  index scan has to prove it.

Queries are REAL embedded questions from the fixtures, never random vectors -
uniform random coordinates in 1,536 dimensions are nearly equidistant, which
measured HNSW at recall 0.04 in slice 4 and said nothing about HNSW.
"""

from __future__ import annotations

import os
import pickle
import statistics
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv

CACHE = Path(".cache/hybrid")
MODEL = "codestral-embed"
DIM = 1536
# pgvector ships 40 and it cost 14% of recall on FastAPI in slice 4. Half a
# millisecond bought it back, so both are measured rather than one assumed.
EF_SEARCH = (40, 100)
REPEATS = 3

EXACT = (
    "select chunk_index from chunks where artifact_id = %s "
    "order by v <=> %s::vector limit 50"
)
# An EXPRESSION index, because `v` is an undimensioned `vector` column and
# pgvector cannot index one - the column stays undimensioned so slice 8 is
# free to choose a model of any width.
INDEXED = (
    f"select chunk_index from chunks where artifact_id = %s "
    f"order by (v::vector({DIM})) <=> %s::vector({DIM}) limit 50"
)


def vectors_for(corpus: str, n: int = 10) -> list:
    path = CACHE / f"{corpus}_{MODEL}_queries.pkl"
    if not path.exists():
        path = CACHE / f"geo_{MODEL}_queries.pkl"
    return pickle.loads(path.read_bytes())[:n]


def run(cur, sql: str, artifact_id: str, vector) -> tuple[float, float, str, list]:
    """Client median, server median, plan node, and the rows."""
    literal = str(list(vector))
    client, rows = [], []
    for _ in range(REPEATS):
        start = time.perf_counter()
        cur.execute(sql, (artifact_id, literal))
        rows = cur.fetchall()
        client.append((time.perf_counter() - start) * 1000)

    cur.execute("explain (analyze, timing off) " + sql, (artifact_id, literal))
    lines = [r[0].strip() for r in cur.fetchall()]
    node = next(
        (x.split("(")[0].strip() for x in lines if "Scan" in x or "Sort" in x), "?"
    )
    server = next(
        (
            float(x.split(":")[1].split()[0])
            for x in lines
            if x.startswith("Execution Time")
        ),
        0.0,
    )
    return statistics.median(client), server, node, [r[0] for r in rows]


def main() -> int:
    load_dotenv(".env")
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=20) as conn:
        conn.autocommit = True
        cur = conn.cursor()
        artifacts = cur.execute(
            "select artifact_id, count(*) from chunks group by 1 order by 2"
        ).fetchall()

        truth: dict[str, list[list[int]]] = {}
        exact_server: dict[str, float] = {}
        print(f"{'artifact':<24}{'rows':>6}{'client ms':>11}{'server ms':>11}  plan")
        for artifact_id, rows in artifacts:
            corpus = artifact_id.replace("B-bench-", "")
            node = "?"
            cls, svs = [], []
            for v in vectors_for(corpus):
                c, s, node, got = run(cur, EXACT, artifact_id, v)
                cls.append(c)
                svs.append(s)
                truth.setdefault(artifact_id, []).append(got)
            exact_server[artifact_id] = statistics.median(svs)
            print(
                f"{artifact_id:<24}{rows:>6}{statistics.median(cls):>11.1f}"
                f"{exact_server[artifact_id]:>11.2f}  {node}",
                flush=True,
            )

        print("\nbuilding one PARTIAL hnsw index per artifact")
        for artifact_id, rows in artifacts:
            name = "hnsw_" + artifact_id.replace("-", "_").lower()
            cur.execute(f"drop index if exists {name}")
            start = time.perf_counter()
            # DDL takes no bind parameter - "could not determine data type of
            # parameter $1" - so the predicate is inlined. The ids are ours.
            cur.execute(
                f"create index {name} on chunks using hnsw "
                f"((v::vector({DIM})) vector_cosine_ops) "
                f"where artifact_id = '{artifact_id}'"
            )
            print(
                f"  {name}: {rows} rows in {time.perf_counter() - start:.1f}s",
                flush=True,
            )
        cur.execute("analyze chunks")

        print(
            f"\n{'artifact':<24}{'rows':>6}{'ef':>4}{'client ms':>11}"
            f"{'server ms':>11}{'vs exact':>10}{'recall@10':>11}  plan"
        )
        for artifact_id, rows in artifacts:
            corpus = artifact_id.replace("B-bench-", "")
            for ef in EF_SEARCH:
                cur.execute(f"set hnsw.ef_search = {ef}")
                cls, svs, recalls, node = [], [], [], "?"
                for i, v in enumerate(vectors_for(corpus)):
                    c, s, node, got = run(cur, INDEXED, artifact_id, v)
                    cls.append(c)
                    svs.append(s)
                    want = set(truth[artifact_id][i][:10])
                    recalls.append(len(want & set(got[:10])) / max(1, len(want)))
                sv = statistics.median(svs)
                kind = "INDEX" if "Index Scan" in node else f"NOT USED - {node}"
                print(
                    f"{artifact_id:<24}{rows:>6}{ef:>4}{statistics.median(cls):>11.1f}"
                    f"{sv:>11.2f}{exact_server[artifact_id] / sv if sv else 0:>9.1f}x"
                    f"{statistics.mean(recalls):>11.3f}  {kind}",
                    flush=True,
                )

        total, idx = cur.execute(
            "select pg_size_pretty(pg_total_relation_size('chunks')), "
            "pg_size_pretty(coalesce(sum(pg_relation_size(indexrelid)), 0)) "
            "from pg_index where indrelid = 'chunks'::regclass"
        ).fetchone()
        print(f"\nchunks total {total}, of which indexes {idx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
