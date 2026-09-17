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
from scripts.score_hybrid import CORPORA

ANSWERS = Path("artifacts/slice8v2/answers")
RESULTS = Path(".logs/results")
NAME = re.compile(r"^(?P<corpus>.+)_n(?P<n>\d+)_(?P<model>.+)\.md$")


def main(argv: list[str]) -> int:
    load_dotenv(".env")
    want = next((a.split("=")[1] for a in argv if a.startswith("--model=")), "")

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
        rows.append(
            {
                "corpus": corpus,
                "chunks": len(chunks),
                "n": n,
                "sent": len(keep),
                "share": len(keep) / len(chunks),
                "model": model,
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

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "answers_regraded.json").write_text(json.dumps(rows, indent=1))
    print(f"\n{len(rows)} replies re-graded, 0 calls spent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
