"""Chunk size, overlap, and whether the context header earns its place.

    PYTHONPATH=. python scripts/sweep_chunking.py size cobra log jq notebooks
    PYTHONPATH=. python scripts/sweep_chunking.py overlap cobra log
    PYTHONPATH=. python scripts/sweep_chunking.py header cobra log jq papers
    PYTHONPATH=. python scripts/sweep_chunking.py task cobra log

THREE DECISIONS THIS PROJECT CALLS PERMANENT AND HAS NEVER MEASURED.

CLAUDE.md says chunking is "the highest-leverage decision in RAG" and that a
bad boundary cannot be repaired by anything downstream - and then pins
`s = 500`, `o = 50` from a formula and a paragraph, ending with an instruction
nobody has carried out: *"Do not tune s by feeling. Change it, re-run, and
look at whether the right chunk comes back."* This is that run.

It is only possible because ground truth is stored as LINE NUMBERS. Re-chunking
moves every boundary and every chunk index; the line that answers a question
does not move, so the same fixture scores a corpus cut four different ways.
That property was chosen for exactly this and has never been used.

`header` is the fourth one, and it is free money if it works: every chunk
already carries `[file - label - lines]`, prepended by `embed_text`. That is
"contextual retrieval" with no LLM call, and this project has assumed it helps
since slice 3 without ever embedding the text without it.

`task` checks whether the query/document asymmetry is worth its complication:
`embed(task="query")` against `embed(task="document")` for the same questions.
Only Cohere and Google implement it; Mistral ignores the argument entirely, so
on codestral this is expected to be a FLAT LINE and is worth confirming rather
than believing.

Every mode spends embedding quota and no generation quota. Vectors are cached
per configuration, so a re-run is free.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv

from labpilot.ingest import _recursive, chunker
from labpilot.ingest import defaults as ingest_defaults
from labpilot.tokens import CHARS_PER_TOKEN, estimate_tokens
from scripts import corpora
from scripts.score_hybrid import EMBEDDERS, embedded

CACHE = Path(".cache/chunking")
RESULTS = Path(".logs/results")

SIZES = (250, 375, 500, 750, 1000)
OVERLAPS = (0, 25, 50, 100)


def apply(size: int, overlap: int) -> None:
    """Point every chunking constant at one configuration.

    Monkeypatching module constants is crude and is the right tool here: the
    alternative is threading four parameters through chunk_file, split_recursive,
    _blocks and _pack for a measurement, and production would then carry the
    knobs forever to serve a script.
    """
    cap = size + 10  # the hard cap sits just above the target, as it ships
    ingest_defaults.CHUNK_SIZE = size
    ingest_defaults.CHUNK_OVERLAP = overlap
    ingest_defaults.MAX_CHUNK_TOKENS = cap
    ingest_defaults.MAX_CHARS = cap * CHARS_PER_TOKEN
    _recursive.TARGET_CHARS = size * CHARS_PER_TOKEN
    _recursive.OVERLAP_CHARS = overlap * CHARS_PER_TOKEN
    _recursive.MAX_CHARS = cap * CHARS_PER_TOKEN
    chunker.MAX_CHARS = cap * CHARS_PER_TOKEN


def score(chunks, queries, chunk_vectors, query_vectors) -> dict:
    """Vector search only - no database, no keyword channel.

    The question here is whether the BOUNDARIES are better, and adding a second
    channel would mix that with how well BM25 copes with them.
    """
    n = len(chunks)
    places = []
    for query, asked in zip(queries, query_vectors, strict=True):
        want = {
            i
            for i, c in enumerate(chunks)
            if c.source == query.file
            and any(c.start_line <= line <= c.end_line for line in query.expects)
        }
        if not want:
            # The answer's line falls in no chunk at this configuration. That
            # is a real property of the cut, not a missing query, so it counts
            # as a miss rather than being dropped - dropping it would let a
            # configuration win by losing the questions it cannot answer.
            places.append(n + 1)
            continue
        order = sorted(
            range(n),
            key=lambda i: (
                -sum(a * b for a, b in zip(asked, chunk_vectors[i], strict=True))
            ),
        )
        places.append(next((p for p, i in enumerate(order, 1) if i in want), n + 1))

    return {
        "r@1": sum(p <= 1 for p in places) / len(places),
        "r@10": sum(p <= 10 for p in places) / len(places),
        "r@50": sum(p <= 50 for p in places) / len(places),
        "MRR": statistics.mean(1 / p for p in places),
        "chunks": n,
        "mean_tokens": round(
            statistics.mean(estimate_tokens(c.embed_text) for c in chunks)
        ),
    }


def vectors(chunks, tag: str, embedder, *, bare: bool = False) -> list:
    texts = [c.text if bare else c.embed_text for c in chunks]
    return embedded(embedder, texts, task="document", tag=tag)


def run(mode: str, names: list[str]) -> None:
    embedder = EMBEDDERS["codestral"]
    CACHE.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for name in names:
        queries = corpora.queries_for(name)
        print(f"\n=== {name} ({len(queries)} queries)")

        if mode == "size":
            settings = [(s, 50) for s in SIZES]
        elif mode == "overlap":
            settings = [(500, o) for o in OVERLAPS]
        else:
            settings = [(500, 50)]

        print(
            f"  {'setting':16} {'chunks':>7} {'tok':>5} {'r@1':>7} "
            f"{'r@10':>7} {'r@50':>7} {'MRR':>7}"
        )

        for size, overlap in settings:
            apply(size, overlap)
            chunks = corpora.chunks_for(name)
            tag = f"{name}_{embedder.model}_s{size}_o{overlap}"

            variants = [("", False)]
            if mode == "header":
                variants = [("+header", False), ("bare", True)]

            for suffix, bare in variants:
                cv = vectors(chunks, f"chunk_{tag}{suffix}", embedder, bare=bare)
                qv = embedded(
                    embedder,
                    [q.text for q in queries],
                    task="document"
                    if mode == "task" and suffix == "asdoc"
                    else "query",
                    tag=f"chunkq_{name}_{embedder.model}",
                )
                got = score(chunks, queries, cv, qv)
                label = f"s={size} o={overlap}{' ' + suffix if suffix else ''}"
                print(
                    f"  {label:16} {got['chunks']:7} {got['mean_tokens']:5} "
                    f"{got['r@1']:7.3f} {got['r@10']:7.3f} {got['r@50']:7.3f} "
                    f"{got['MRR']:7.3f}",
                    flush=True,
                )
                rows.append({"corpus": name, "mode": mode, "label": label, **got})

        if mode == "task":
            chunks = corpora.chunks_for(name)
            cv = vectors(chunks, f"chunk_{name}_{embedder.model}_s500_o50", embedder)
            for task in ("query", "document"):
                qv = embedded(
                    embedder,
                    [q.text for q in queries],
                    task=task,
                    tag=f"chunkq_{name}_{embedder.model}_{task}",
                )
                got = score(chunks, queries, cv, qv)
                print(
                    f"  task={task:9}   {got['chunks']:7} {got['mean_tokens']:5} "
                    f"{got['r@1']:7.3f} {got['r@10']:7.3f} {got['r@50']:7.3f} "
                    f"{got['MRR']:7.3f}",
                    flush=True,
                )
                rows.append(
                    {"corpus": name, "mode": mode, "label": f"task={task}", **got}
                )

    apply(500, 50)  # leave the constants as they ship
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"chunking_{mode}.json").write_text(json.dumps(rows, indent=1))

    print(f"\npooled across {len(names)} corpora, {mode}")
    pools: dict[str, list[float]] = {}
    for row in rows:
        pools.setdefault(row["label"], []).append(row["MRR"])
    for label, values in sorted(pools.items(), key=lambda kv: -statistics.mean(kv[1])):
        print(f"  {label:18} mean MRR {statistics.mean(values):.3f}  n={len(values)}")


if __name__ == "__main__":
    load_dotenv(".env")
    if len(sys.argv) < 3 or sys.argv[1] not in {"size", "overlap", "header", "task"}:
        raise SystemExit(f"usage: {sys.argv[0]} size|overlap|header|task <corpus>...")
    run(sys.argv[1], sys.argv[2:])
