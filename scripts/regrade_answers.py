"""Re-score the SAVED replies, spending nothing.

    PYTHONPATH=. python scripts/regrade_answers.py
    PYTHONPATH=. python scripts/regrade_answers.py --model=gemini-3.5-flash-lite

WHY THIS EXISTS. `score_answers.py` writes every reply to
`artifacts/slice8v2/answers/` before grading it, so the model output is data
on disk and the grader is just a function over it. When the grader turns out
to be wrong - and it was: the citation regex demanded `[B-12 "line"]` and
scored `[B-12] "line"` as no citation at all - the fix must not cost a single
call. It costs none.

That is the whole argument for saving raw output beside every number. The
first version of this measurement reported a corpus as "20 answered, 0 cited,
0 correct" at N=100, which reads like a model collapsing under a long prompt.
It was a missing space in a regular expression, and only the saved reply could
tell those apart.

The chunks that were sent are NOT stored, because they do not need to be:
`chosen()` is deterministic over the cached embeddings, so the exact set is
recomputed for free.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv

from scripts.score_answers import chosen, grade
from scripts.score_hybrid import CORPORA, targets

ANSWERS = Path("artifacts/slice8v2/answers")
RESULTS = Path(".logs/results")
NAME = re.compile(r"^(?P<corpus>.+)_n(?P<n>\d+)_(?P<model>.+)\.md$")


ANSWERABLE_FLOOR = 8


def per_corpus(rows: list[dict], model: str) -> None:
    """Is the best N a COUNT, or a share of the corpus?

    The question DECISIONS.md posed before the run: N=20 is 26% of an 78-chunk
    artifact and 2% of a 1,160-chunk one, and those predict opposite things.

        flat across corpus sizes  -> it is about the COUNT
        tracks a percentage       -> it is about COVERAGE

    Cells are hidden where fewer than ANSWERABLE_FLOOR questions could have
    been answered from what was sent. THIS IS NOT COSMETIC. USED is a ratio,
    and at N=5 the whole thirteen-corpus panel has under three answerable
    questions per corpus - so eight corpora score a perfect 1.000 from two of
    two, and a naive reading of the same table says the best N is 5. A
    denominator that small measures the fixture, not the model.
    """
    by: dict[str, dict[int, dict]] = {}
    for r in rows:
        if r["model"] == model:
            by.setdefault(r["corpus"], {})[r["n"]] = r
    if not by:
        return
    sizes = sorted({n for d in by.values() for n in d})

    print()
    print(
        f"{model} - PER CORPUS: USED, where at least {ANSWERABLE_FLOOR} "
        f"questions were answerable"
    )
    head = "".join(f"{'N=' + str(n):<8}" for n in sizes)
    print(f"  {'corpus':11}{'chunks':>7}  " + head)

    counts: list[int] = []
    shares: list[float] = []

    def size_of(item):
        return next(iter(item[1].values()))["chunks"]

    for corpus, d in sorted(by.items(), key=size_of):
        chunks = next(iter(d.values()))["chunks"]
        cells, best, best_n = [], -1.0, None
        for n in sizes:
            r = d.get(n)
            if not r:
                cells.append(f"{'-':<8}")
                continue
            if r["answerable"] < ANSWERABLE_FLOOR:
                cells.append(f"{'(' + str(r['answerable']) + ')':<8}")
                continue
            used = r["correct"] / r["answerable"]
            cells.append(f"{used:<8.3f}")
            if used > best:
                best, best_n = used, n
        tail = f"  best N={best_n}" if best_n else "  (never enough)"
        print(f"  {corpus:11}{chunks:7}  " + "".join(cells) + tail)
        if best_n:
            counts.append(best_n)
            shares.append(best_n / chunks)

    if len(counts) < 2:
        return
    cv_count = statistics.stdev(counts) / statistics.mean(counts)
    cv_share = statistics.stdev(shares) / statistics.mean(shares)
    print()
    print(
        f"  best N as a COUNT: median {statistics.median(counts):g}, "
        f"{min(counts)}-{max(counts)}, cv {cv_count:.2f}"
    )
    print(
        f"  best N as a SHARE: {min(shares):.0%}-{max(shares):.0%}, cv {cv_share:.2f}"
    )
    verdict = "COUNT" if cv_count < cv_share else "COVERAGE"
    print(f"  the smaller cv is the constant one -> N is about the {verdict}")


def main(argv: list[str]) -> int:
    load_dotenv(".env")
    want = next((a.split("=")[1] for a in argv if a.startswith("--model=")), "")

    # The token cost of each prompt comes from the RUN, not from here.
    # Recomputing it would mean rebuilding the exact prompt string, and a
    # second implementation of a number is a second chance to disagree with
    # the first. An earlier version of this file guessed it and silently
    # printed "fits gemma: 10 of 10" at every N, including at 42,000 tokens.
    costs: dict[tuple[str, int, str], dict] = {}
    for run in RESULTS.glob("answers_*.json"):
        if run.name == "answers_regraded.json":
            continue
        for r in json.loads(run.read_text()):
            costs[(r["corpus"], r["n"], r["model"])] = r

    loaded: dict[str, tuple] = {}
    rows: list[dict] = []
    for path in sorted(ANSWERS.glob("*.md")):
        match = NAME.match(path.name)
        if not match:
            continue
        corpus, n, model = match["corpus"], int(match["n"]), match["model"]
        if corpus not in CORPORA or (want and model != want):
            continue
        if corpus not in loaded:
            loaded[corpus] = CORPORA[corpus]()
        chunks, queries = loaded[corpus]

        keep = chosen(chunks, queries, corpus, n)
        got = grade(path.read_text(encoding="utf-8"), chunks, queries, keep)
        # HOW MANY QUESTIONS COULD EVEN BE ANSWERED from what was sent.
        #
        # `correct / asked` mixes two different things that move together and
        # mean opposite things: whether retrieval PUT the answer in the prompt,
        # and whether the model USED it. The first is recall, already measured
        # to rise with N by construction. The second is the generation term
        # this whole experiment exists for, and it is the one that would show
        # dilution if dilution were happening.
        #
        # The fixtures carry ground truth, so the split is free: a question is
        # ANSWERABLE when a chunk holding its answer is in the set we sent.
        sent = set(keep)
        answerable = sum(1 for q in queries if targets(chunks, q) & sent)
        cost = costs.get((corpus, n, model), {})
        rows.append(
            {
                "corpus": corpus,
                "chunks": len(chunks),
                "n": n,
                "sent": len(keep),
                "share": len(keep) / len(chunks),
                "model": model,
                "tokens": cost.get("tokens"),
                "padded": cost.get("padded"),
                "fits_gemma": cost.get("fits_gemma"),
                "answerable": answerable,
                **got,
            }
        )

    if not rows:
        print("no saved replies matched")
        return 1

    models = sorted({r["model"] for r in rows})
    for model in models:
        mine = [r for r in rows if r["model"] == model]
        print(f"\n{model} - {len({r['corpus'] for r in mine})} corpora")
        print(
            f"  {'N':>4} {'corpora':>8} {'mean share':>11} {'answered':>9} "
            f"{'cited':>7} {'CORRECT':>8} {'correct/asked':>14}"
        )
        for n in sorted({r["n"] for r in mine}):
            got = [r for r in mine if r["n"] == n]
            asked = sum(r["asked"] for r in got)
            print(
                f"  {n:4} {len(got):8} "
                f"{sum(r['share'] for r in got) / len(got):11.0%} "
                f"{sum(r['answered'] for r in got):9} "
                f"{sum(r['cited'] for r in got):7} "
                f"{sum(r['correct'] for r in got):8} "
                f"{sum(r['correct'] for r in got) / asked:14.3f}"
            )

    # A BALANCED PANEL, because the pooled table above is not one.
    #
    # Only corpora with at least 100 chunks can be asked for N=100, so the
    # N=100 row is computed over a DIFFERENT and systematically larger set of
    # corpora than the N=5 row. Comparing them directly confounds "more chunks
    # help" with "big corpora are harder", and those predict opposite things.
    #
    # This restricts to the corpora that answered at EVERY N, so each column
    # is the same corpora and the only thing that changes is N.
    for model in models:
        mine = [r for r in rows if r["model"] == model]
        sizes = sorted({r["n"] for r in mine})
        reached = {
            c
            for c in {r["corpus"] for r in mine}
            if {r["n"] for r in mine if r["corpus"] == c} == set(sizes)
        }
        if not reached or len(reached) < 2:
            continue
        print()
        print(
            f"{model} - BALANCED PANEL: the {len(reached)} corpora that "
            f"answered at every N"
        )
        print(f"  {', '.join(sorted(reached))}")
        print(
            f"  {'N':>4} {'mean share':>11} {'mean tokens':>12} "
            f"{'answerable':>11} {'CORRECT':>8} {'correct/asked':>14} "
            f"{'USED':>7} {'fits gemma':>11}"
        )
        for n in sizes:
            got = [r for r in mine if r["n"] == n and r["corpus"] in reached]
            asked = sum(r["asked"] for r in got)
            known = [r for r in got if r["fits_gemma"] is not None]
            fits = (
                f"{sum(1 for r in known if r['fits_gemma'])} of {len(known)}"
                if known
                else "unknown"
            )
            tokens = [r["tokens"] for r in got if r["tokens"]]
            able = sum(r["answerable"] for r in got)
            right = sum(r["correct"] for r in got)
            print(
                f"  {n:4} {sum(r['share'] for r in got) / len(got):11.0%} "
                f"{(sum(tokens) // len(tokens)) if tokens else 0:12} "
                f"{able:11} {right:8} {right / asked:14.3f} "
                f"{(right / able if able else 0):7.3f} {fits:>11}"
            )
        print(
            "  USED = correct / answerable: of the questions whose answer WAS "
            "in the prompt, how many the model got right"
        )

    for model in models:
        per_corpus(rows, model)

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "answers_regraded.json").write_text(json.dumps(rows, indent=1))
    print(f"\n{len(rows)} replies re-graded, 0 calls spent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
