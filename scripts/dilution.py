"""Is there a dilution penalty, on questions held FIXED?

    PYTHONPATH=. python scripts/dilution.py
    PYTHONPATH=. python scripts/dilution.py --from=30

COSTS NOTHING. It re-reads the saved replies in `artifacts/slice8v2/answers/`
and recomputes which chunks were sent, which is deterministic over the cached
embeddings.

WHY A PLAIN `correct / answerable` IS NOT ENOUGH, and this is the whole point
of the file. That ratio falls as N rises, and the obvious reading is dilution:
the model is given more and uses less of it. But the questions that only BECOME
answerable at N=100 are exactly the ones whose answer chunk retrieval ranked
51st to 100th - the hard ones. So a falling ratio may be measuring the changing
DIFFICULTY MIX rather than the length of the prompt, and the two are
indistinguishable in the pooled number.

Measured, that confound is most of the effect:

    unrestricted   USED 0.983 at N=20 -> 0.851 at N=100   (-13 points)
    fixed set      USED 0.983 at N=20 -> 0.906 at N=100   (-8 points)

So the honest instrument holds the questions still. This restricts to the
questions whose answer was in the prompt at EVERY N, and then compares them
PAIRWISE - question by question, not as two averages - because the same
question answered under two prompt lengths is a paired observation and
throwing that away costs most of the power.

The test is a two-sided sign test over the questions that CHANGED, which is
the only thing a paired binary comparison can be asked. Questions right in
both, or wrong in both, carry no information about the difference and are
correctly ignored.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from scripts.score_answers import ANSWER, CITATION, chosen
from scripts.score_hybrid import CORPORA, targets

ANSWERS = Path("artifacts/slice8v2/answers")
NAME = re.compile(r"^(?P<corpus>.+)_n(?P<n>\d+)_(?P<model>.+)\.md$")
SIZES = (5, 10, 20, 30, 50, 100)


def sign_test(lost: int, gained: int) -> float:
    """Two-sided sign test. Under "the prompt length does not matter", a
    question that changed is equally likely to have changed either way."""
    changed = lost + gained
    if changed == 0:
        return 1.0
    fewer = min(lost, gained)
    tail = sum(math.comb(changed, i) for i in range(fewer + 1)) / 2**changed
    return min(1.0, 2 * tail)


def load(model: str) -> dict[tuple[str, int], dict[str, tuple[bool, bool]]]:
    data: dict[tuple[str, int], dict[str, tuple[bool, bool]]] = {}
    loaded: dict[str, tuple] = {}
    for path in sorted(ANSWERS.glob(f"*{model}.md")):
        match = NAME.match(path.name)
        if not match or match["corpus"] not in CORPORA:
            continue
        corpus, n = match["corpus"], int(match["n"])
        if corpus not in loaded:
            loaded[corpus] = CORPORA[corpus]()
        chunks, queries = loaded[corpus]
        sent = set(chosen(chunks, queries, corpus, n))
        said = {
            int(num): text
            for num, text in ANSWER.findall(path.read_text(encoding="utf-8"))
        }
        out: dict[str, tuple[bool, bool]] = {}
        for i, query in enumerate(queries, 1):
            want = targets(chunks, query)
            text = said.get(i, "")
            correct = False
            if text and "NOT IN THE EXTRACTS" not in text.upper():
                cited = {int(c.split("-")[1]) for c in CITATION.findall(text)}
                correct = bool(cited & want) and cited <= sent
            out[query.id] = (bool(want & sent), correct)
        data[(corpus, n)] = out
    return data


def main(argv: list[str]) -> int:
    load_dotenv(".env")
    model = next(
        (a.split("=")[1] for a in argv if a.startswith("--model=")),
        "gemini-3.5-flash-lite",
    )
    start = int(next((a.split("=")[1] for a in argv if a.startswith("--from=")), "20"))
    sizes = tuple(n for n in SIZES if n >= start)

    data = load(model)
    if not data:
        print("no saved replies found")
        return 1

    corpora = [
        c for c in sorted({c for c, _ in data}) if all((c, n) in data for n in sizes)
    ]
    fixed: list[tuple[str, set[str]]] = []
    for corpus in corpora:
        ids = set(data[(corpus, sizes[0])])
        for n in sizes:
            ids &= {q for q, (able, _) in data[(corpus, n)].items() if able}
        fixed.append((corpus, ids))
    total = sum(len(ids) for _, ids in fixed)
    if not total:
        print("no question is answerable at every N in that range")
        return 1

    print(
        f"{model} - FIXED QUESTION SET: {total} questions over {len(corpora)} "
        f"corpora, answerable at every N in {sizes}"
    )
    print(f"  one question is {1 / total:.3f} of the score")
    print()
    print(f"  {'N':>4} {'correct':>8} {'USED':>8}")
    for n in sizes:
        right = sum(1 for c, ids in fixed for q in ids if data[(c, n)][q][1])
        print(f"  {n:4} {right:8} {right / total:8.3f}")

    print()
    print("  PAIRED, question by question - the answer was in the prompt BOTH times")
    print(
        f"  {'pair':16} {'right->WRONG':>13} {'wrong->right':>13} {'net':>6}"
        f" {'sign test':>11}"
    )
    for i, lo in enumerate(sizes):
        for hi in sizes[i + 1 :]:
            lost = sum(
                1
                for c, ids in fixed
                for q in ids
                if data[(c, lo)][q][1] and not data[(c, hi)][q][1]
            )
            gained = sum(
                1
                for c, ids in fixed
                for q in ids
                if not data[(c, lo)][q][1] and data[(c, hi)][q][1]
            )
            print(
                f"  N={lo:<4}-> N={hi:<6} {lost:13} {gained:13} "
                f"{gained - lost:+6} {sign_test(lost, gained):11.3f}"
            )
    print()
    print(
        "  a question right in both, or wrong in both, says nothing about the "
        "difference and is correctly ignored by the test"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
