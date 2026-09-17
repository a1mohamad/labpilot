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
import statistics
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
        f"{'before':>7} {'after':>7} {'delta':>7} {'in q':>7} {'verdict':8}  check"
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

        # AGAINST WHAT THIS FIXTURE CAN RESOLVE, not against zero.
        #
        # One query moving from first place to second changes MRR by
        # 0.5/queries. On the 13-query gson that is 0.038; on the 45-query geo
        # it is 0.011. So the same -0.03 is one query on one corpus and three
        # on another, and a table printing "hurt" for both compares a
        # measurement with a wobble. RESUME.md states the rule; nothing
        # applied it.
        resolution = 0.5 / run["queries"]
        queries = (after - before) / resolution
        if abs(queries) > 2:
            verdict = "REAL"
        elif abs(queries) < 1:
            verdict = "noise"
        else:
            verdict = "marginal"
        print(
            f"{run['reranker']:24} {run['corpus']:11} {run['window']:4} "
            f"{run['chunks']:7} {before:7.3f} {after:7.3f} {after - before:+7.3f}"
            f" {queries:+6.1f}q {verdict:8}  {check}"
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
    print(
        "  'helped' and 'hurt' count against ZERO; the per-run verdict column "
        "counts against what each fixture can resolve, which is the honest one"
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


def facets() -> dict[str, dict]:
    """What each corpus IS, read from its own fixture.

    Thirteen corpora can be grouped; three could not. Every earlier
    conclusion in this project is a per-corpus one, and the first slice 8 run
    read "Go chunks are big" off a single Go corpus when the real property was
    "no AST splitter".
    """
    from scripts import corpora

    out: dict[str, dict] = {}
    for name, spec in corpora.SPECS.items():
        splitter = spec.get("splitter", "?")
        out[name] = {
            "language": spec.get("language", "?"),
            "splitter": splitter,
            "format": "prose"
            if splitter in {"pdf-page", "markdown-header"}
            else "notebook"
            if splitter == "notebook-cell"
            else "code",
        }
    out["quora"] = {"language": "Python", "splitter": "python-ast", "format": "code"}
    return out


def grouped(runs: dict[str, dict], metric: str, bm25: str, by: str) -> None:
    """One ranker's score, pooled by a property of the corpus or the query.

    `wording` and `kind` pool per QUERY, which needs the per-query places the
    scorer now saves; the rest pool per CORPUS.
    """
    info = facets()
    pools: dict[str, list[float]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)

    for corpus, data in runs.items():
        scores = data["by_bm25"][bm25]
        if by in {"wording", "kind"}:
            labels = data.get("wording" if by == "wording" else "kinds", {})
            places = scores.get(BASELINE, {}).get("places")
            if not places or not labels:
                continue
            for query_id, place in places.items():
                key = labels.get(query_id, "?")
                pools[key].append(1 / place)
                counts[key] += 1
        else:
            key = info.get(corpus, {}).get(by, "?")
            pools[key].append(scores[BASELINE][metric])
            counts[key] += 1

    unit = "queries" if by in {"wording", "kind"} else "corpora"
    label = "MRR" if by in {"wording", "kind"} else metric
    print(f"\nvector alone, pooled by {by} ({label})")
    print(f"  {by:16} {unit:>8} {'mean':>7} {'worst':>7} {'best':>7}")
    for key, values in sorted(pools.items(), key=lambda kv: -statistics.mean(kv[1])):
        print(
            f"  {key:16} {counts[key]:8} {statistics.mean(values):7.3f} "
            f"{min(values):7.3f} {max(values):7.3f}"
        )


def deltas_by(runs: dict[str, dict], bm25: str, by: str) -> None:
    """Each ranker's gain over vector, pooled by a property of the QUERY.

    THE QUESTION THIS EXISTS FOR. The case for a keyword channel in this
    project is one sentence: "vectors are good at meaning, keywords are good
    at names, and code is mostly names." Every fixture labels each query
    `named` (it shares a word with the code) or `paraphrase` (it deliberately
    does not), and nothing had ever read the label.

    If the claim holds, BM25's gain over vector must be clearly larger on
    `named` than on `paraphrase`. Pooling the ABSOLUTE score by wording cannot
    show that - an easy corpus lifts both groups - so this pools the
    DIFFERENCE, per query, which is paired and therefore far more sensitive.
    """
    pools: dict[tuple[str, str], list[float]] = defaultdict(list)

    for data in runs.values():
        scores = data["by_bm25"][bm25]
        labels = data.get("wording" if by == "wording" else "kinds", {})
        base = scores.get(BASELINE, {}).get("places")
        if not base or not labels:
            continue
        for ranker, got in scores.items():
            if ranker == BASELINE or "places" not in got:
                continue
            for query_id, place in got["places"].items():
                if query_id not in base:
                    continue
                key = labels.get(query_id, "?")
                pools[(ranker, key)].append(1 / place - 1 / base[query_id])

    groups = sorted({k for _, k in pools})
    print()
    print(f"gain over vector alone (MRR), pooled by {by} - {len(runs)} corpora")
    print(f"  {'ranker':22} " + " ".join(f"{g:>18}" for g in groups))
    for ranker in sorted({r for r, _ in pools}):
        cells = []
        for g in groups:
            vals = pools.get((ranker, g), [])
            cells.append(
                f"{statistics.mean(vals):+8.3f} n={len(vals):<3}" if vals else " " * 18
            )
        print(f"  {ranker:22} " + " ".join(f"{c:>18}" for c in cells))
    print(
        "  (positive means the ranker beat vector on that group; the "
        "comparison is PAIRED, query by query)"
    )
    if by == "wording" and {"named", "paraphrase"} <= set(groups):
        named = pools.get(("bm25", "named"), [])
        para = pools.get(("bm25", "paraphrase"), [])
        if named and para:
            print()
            print(
                f"  THE HYBRID-SEARCH PREMISE: bm25 over vector is "
                f"{statistics.mean(named):+.3f} on named and "
                f"{statistics.mean(para):+.3f} on paraphrase - "
                f"a gap of {statistics.mean(named) - statistics.mean(para):+.3f}"
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

    delta_by = next((a.split("=")[1] for a in argv if a.startswith("--delta-by=")), "")
    if delta_by:
        deltas_by(runs, bm25, delta_by)
        return 0

    by = next((a.split("=")[1] for a in argv if a.startswith("--by=")), "")
    if by:
        grouped(runs, metric, bm25, by)
        return 0

    headroom(runs, bm25)
    table(runs, metric, bm25)
    for facet in ("format", "splitter", "language"):
        grouped(runs, metric, bm25, facet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
