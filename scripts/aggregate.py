"""Turn many per-corpus runs into one claim that can be defended.

    PYTHONPATH=. python scripts/aggregate.py --metric=MRR
    PYTHONPATH=. python scripts/aggregate.py --metric=r@50 --embedder=codestral-embed

Slice 5 and slice 6 both decided on ONE corpus and were both overturned by the
second one. With thirteen corpora the failure mode is the opposite: thirteen
printed tables, and a conclusion drawn from whichever one was read last.

So this reads the JSON every run writes and applies CLAUDE.md's own rule -
judge a method by HOW MANY INDEPENDENT WAYS it was shown better, never by its
best single number:

    wins    corpora where it beat the baseline
    losses  corpora where it lost                 <- the column that decides
    worst   its biggest single loss               <- an average hides this

A method that never loses is a candidate. A method with a big average and one
bad corpus is a number, not evidence.

SATURATION IS REPORTED, because a corpus at r@50 = 1.000 cannot show a gain
and must not be counted as a tie. Slice 5's whole conclusion was a statement
about two saturated corpora that had nothing left to win.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path(".logs/results")
BASELINE = "vector"


def load(embedder: str | None) -> dict[str, dict]:
    runs: dict[str, dict] = {}
    for path in sorted(RESULTS.glob("hybrid_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if embedder and data["embedder"] != embedder:
            continue
        runs[data["corpus"]] = data
    return runs


def table(runs: dict[str, dict], metric: str, bm25: str) -> None:
    corpora = sorted(runs, key=lambda c: runs[c]["chunks"])
    rankers: dict[str, dict[str, float]] = defaultdict(dict)
    for corpus, data in runs.items():
        for label, scores in data["by_bm25"][bm25].items():
            rankers[label][corpus] = scores[metric]

    head = "".join(f"{c[:8]:>9}" for c in corpora)
    print(f"\n{metric} by corpus, smallest first\n{'ranker':26}{head}")
    for label, by_corpus in rankers.items():
        row = "".join(f"{by_corpus.get(c, float('nan')):9.3f}" for c in corpora)
        print(f"{label:26}{row}")

    print(f"\nagainst `{BASELINE}`, {metric}")
    print(f"{'ranker':26} {'wins':>5} {'ties':>5} {'loss':>5} {'worst':>7} {'mean':>7}")
    for label, by_corpus in rankers.items():
        if label == BASELINE:
            continue
        deltas = [
            by_corpus[c] - rankers[BASELINE][c]
            for c in corpora
            if c in by_corpus and c in rankers[BASELINE]
        ]
        if not deltas:
            continue
        wins = sum(d > 0.001 for d in deltas)
        losses = sum(d < -0.001 for d in deltas)
        ties = len(deltas) - wins - losses
        verdict = "  NEVER WORSE" if not losses else ""
        print(
            f"{label:26} {wins:5} {ties:5} {losses:5} {min(deltas):+7.3f} "
            f"{sum(deltas) / len(deltas):+7.3f}{verdict}"
        )


def headroom(runs: dict[str, dict], bm25: str) -> None:
    """How much room each corpus has left, so a tie can be read correctly."""
    print(f"\n{'corpus':12} {'chunks':>7} {'queries':>8} {'r@50':>7} {'headroom':>9}")
    for corpus in sorted(runs, key=lambda c: runs[c]["chunks"]):
        data = runs[corpus]
        base = data["by_bm25"][bm25][BASELINE]
        room = 1.0 - base["r@50"]
        flag = "  SATURATED" if room < 0.02 else ""
        print(
            f"{corpus:12} {data['chunks']:7} {data['queries']:8} "
            f"{base['r@50']:7.3f} {room:9.3f}{flag}"
        )


def reranking(metric: str) -> None:
    """Every rerank run, grouped by model and window.

    The question slice 6 could not answer and slice 8's first pass answered on
    one new corpus: does reranking help, and is the answer about RERANKING or
    about one model. With twelve corpora it becomes countable.

    `r@50 moved` is the instrument check, not a result. A reranker only
    reorders what it was given, so if the ceiling moves the measurement is
    broken - the same class of check that caught slice 4's identical vectors.
    """
    runs = []
    for path in sorted(RESULTS.glob("rerank_*.json")):
        runs.append(json.loads(path.read_text(encoding="utf-8")))
    if not runs:
        print("no rerank runs yet")
        return

    print(
        f"\n{'reranker':24} {'corpus':11} {'win':>4} {'chunks':>7} "
        f"{'before':>7} {'after':>7} {'delta':>7}  check"
    )
    by_model: dict[str, list[float]] = defaultdict(list)
    for run in sorted(runs, key=lambda r: (r["reranker"], r["chunks"])):
        before = run["results"]["vector alone"][metric]
        after = run["results"]["vector -> rerank"][metric]
        moved = abs(
            run["results"]["vector alone"]["r@50"]
            - run["results"]["vector -> rerank"]["r@50"]
        )
        check = "ok" if moved < 1e-9 else f"BROKEN r@50 moved {moved:+.3f}"
        by_model[run["reranker"]].append(after - before)
        print(
            f"{run['reranker']:24} {run['corpus']:11} {run['window']:4} "
            f"{run['chunks']:7} {before:7.3f} {after:7.3f} {after - before:+7.3f}"
            f"  {check}"
        )

    print(
        f"\n{'reranker':24} {'corpora':>8} {'helped':>7} {'hurt':>6} "
        f"{'worst':>7} {'mean':>7}"
    )
    for model, deltas in by_model.items():
        helped = sum(d > 0.001 for d in deltas)
        hurt = sum(d < -0.001 for d in deltas)
        print(
            f"{model:24} {len(deltas):8} {helped:7} {hurt:6} "
            f"{min(deltas):+7.3f} {sum(deltas) / len(deltas):+7.3f}"
        )

    # The routing claim. Slice 6 built one on a single model's failure; it is
    # only evidence if the sign is the same model after model, corpus after
    # corpus.
    print("\nby question kind, mean MRR delta (all runs)")
    kinds: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        for asks, got in run["by_kind"].items():
            kinds[asks].append(got["after"] - got["before"])
    for asks, deltas in sorted(kinds.items()):
        negatives = sum(d < -0.001 for d in deltas)
        print(
            f"  {asks:11} n={len(deltas):3} mean {sum(deltas) / len(deltas):+7.3f} "
            f"worst {min(deltas):+7.3f}  negative on {negatives} of {len(deltas)}"
        )


def main(argv: list[str]) -> int:
    metric = next((a.split("=")[1] for a in argv if a.startswith("--metric=")), "MRR")
    embedder = next(
        (a.split("=")[1] for a in argv if a.startswith("--embedder=")),
        "codestral-embed",
    )
    if "--rerank" in argv:
        reranking(metric)
        return 0

    runs = load(embedder)
    if not runs:
        print(f"no runs found in {RESULTS} for {embedder}")
        return 1

    bm25 = next(iter(next(iter(runs.values()))["by_bm25"]))
    print(f"{len(runs)} corpora, embedder {embedder}, BM25 {bm25}")
    headroom(runs, bm25)
    table(runs, metric, bm25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
