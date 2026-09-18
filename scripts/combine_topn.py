"""TOP-N over 18 corpora, ONE model - and the three damaged cells inside it.

v2's 13 corpora and this run's 5 Python ones were both scored on
`gemini-3.5-flash-lite`, so they combine. Take one of the new run used gemma31
and could not be combined with anything.

THE THING THIS SCRIPT EXISTS TO CATCH. A cell with `answered > 0` and
`cited == 0` is a GRADING failure, not a result: the model replied and not one
citation resolved, so `correct` is 0 by construction. v2's own data has three,
and TWO OF THE THREE SIT ON N=30 - the same shape that voided the gemma run,
in the data we were about to trust instead of it.

So every number is printed twice: over all 18, and over the 15 corpora with no
damaged cell. If the two disagree, the damaged cells are the finding.
"""

from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

NS = (10, 20, 30)

# From scripts/zoo.py, which computes the share rather than leaving it to be
# counted by hand. `papers` is English prose and `docs` is Markdown - both were
# wrong in a first draft of this file, which is exactly why the zoo owns it.
PYTHON = {
    "quora",
    "smsspam",
    "disaster",
    "titanic",
    "requests",
    "notebooks",
    "lung",
    "lunghand",
    "click",
    "pytest",
    "pytesthand",
    "pydantic",
    "pydantichand",
}


def rows(path: Path) -> list[dict]:
    return [r for r in json.loads(path.read_text()) if r["n"] in NS]


def damaged(cell: dict) -> bool:
    return cell["answered"] > 0 and cell["cited"] == 0


def report(full: dict[str, dict[int, dict]], label: str) -> None:
    print(f"--- {label}: {len(full)} corpora, {len(set(full) & PYTHON)} Python ---")

    print("  POOLED, every question weighted once")
    for n in NS:
        num = sum(v[n]["correct"] for v in full.values())
        den = sum(v[n]["asked"] for v in full.values())
        ans = sum(v[n]["answered"] for v in full.values())
        print(
            f"    N={n:<3} correct {num:4}/{den}  = {num / den:.3f}"
            f"   answered {ans / den:.3f}"
        )

    print("  PER CORPUS, every corpus weighted once")
    for n in NS:
        share = [v[n]["correct"] / v[n]["asked"] for v in full.values()]
        print(f"    N={n:<3} mean {st.mean(share):.3f}   median {st.median(share):.3f}")

    tally = {n: 0 for n in NS}
    ties = 0
    for v in full.values():
        top = max(v[n]["correct"] for n in NS)
        win = [n for n in NS if v[n]["correct"] == top]
        if len(win) > 1:
            ties += 1
        else:
            tally[win[0]] += 1
    print("  WINS  " + "  ".join(f"N={n} {tally[n]}" for n in NS) + f"   tied {ties}")

    for title, pick in (
        ("PYTHON", lambda c: c in PYTHON),
        ("other ", lambda c: c not in PYTHON),
    ):
        sub = {c: v for c, v in full.items() if pick(c)}
        if not sub:
            continue
        line = f"  {title} n={len(sub):<3}"
        for n in NS:
            num = sum(v[n]["correct"] for v in sub.values())
            den = sum(v[n]["asked"] for v in sub.values())
            line += f"  N={n} {num / den:.3f}"
        print(line)

    for title, lo, hi in (
        ("<500 ", 0, 500),
        ("500-5k", 500, 5000),
        (">5k  ", 5000, 10**9),
    ):
        sub = {c: v for c, v in full.items() if lo <= v[10]["chunks"] < hi}
        if not sub:
            continue
        line = f"  {title} n={len(sub):<3}"
        for n in NS:
            num = sum(v[n]["correct"] for v in sub.values())
            den = sum(v[n]["asked"] for v in sub.values())
            line += f"  N={n} {num / den:.3f}"
        print(line)
    print()


def main(v2: str, v3: str) -> int:
    data = rows(Path(v2)) + rows(Path(v3))

    models = {r["model"] for r in data}
    if len(models) != 1:
        print(f"REFUSING: {len(models)} models in one table: {models}")
        return 1

    by: dict[str, dict[int, dict]] = {}
    for r in data:
        by.setdefault(r["corpus"], {})[r["n"]] = r
    full = {c: v for c, v in by.items() if all(n in v for n in NS)}

    print(f"model   {models.pop()}")
    print(
        f"corpora {len(full)}, {len(set(full) & PYTHON)} Python, "
        f"{sum(v[10]['asked'] for v in full.values())} questions"
    )
    print()

    bad = [(c, n) for c, v in full.items() for n in NS if damaged(v[n])]
    print(
        f"DAMAGED CELLS - answered > 0 and cited == 0: {len(bad)} of "
        f"{len(full) * len(NS)}"
    )
    for c, n in bad:
        cell = full[c][n]
        print(
            f"  {c:11} N={n:<3} answered {cell['answered']:3} "
            f"cited {cell['cited']:3} -> correct forced to 0"
        )
    on_n = {n: sum(1 for _, k in bad if k == n) for n in NS}
    print("  spread across N: " + "  ".join(f"N={n} {on_n[n]}" for n in NS))
    print()

    print(f"{'corpus':12}{'chunks':>7}{'q':>4}  ", end="")
    for n in NS:
        print(f"{'N=' + str(n):>7}", end="")
    print("   best")
    for c, v in sorted(full.items(), key=lambda kv: kv[1][10]["chunks"]):
        mark = "*" if c in PYTHON else " "
        print(f"{mark}{c:11}{v[10]['chunks']:7}{v[10]['asked']:4}  ", end="")
        for n in NS:
            flag = "!" if damaged(v[n]) else " "
            print(f"{v[n]['correct']:6}{flag}", end="")
        top = max(v[n]["correct"] for n in NS)
        win = [n for n in NS if v[n]["correct"] == top]
        print(f"   {'tie' if len(win) > 1 else 'N=' + str(win[0])}")
    print()

    report(full, "ALL, damaged cells included")
    clean = {c: v for c, v in full.items() if not any(damaged(v[n]) for n in NS)}
    report(clean, "CLEAN, every corpus with a damaged cell dropped")
    return 0


V2 = ".logs/results/answers_flashlite.json"  # 13 corpora, N=5..100
V3 = ".logs/results/answers_flashlite_py.json"  # 5 Python corpora, N=10,20,30


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(main(*(args if len(args) == 2 else (V2, V3))))
