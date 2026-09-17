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
import sys
from pathlib import Path

from dotenv import load_dotenv

from scripts.score_answers import chosen, grade
from scripts.score_hybrid import CORPORA, targets

ANSWERS = Path("artifacts/slice8v2/answers")
RESULTS = Path(".logs/results")
NAME = re.compile(r"^(?P<corpus>.+)_n(?P<n>\d+)_(?P<model>.+)\.md$")


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

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "answers_regraded.json").write_text(json.dumps(rows, indent=1))
    print(f"\n{len(rows)} replies re-graded, 0 calls spent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
