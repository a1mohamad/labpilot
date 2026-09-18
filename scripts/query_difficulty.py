"""How HARD is each fixture's queries, measured rather than judged.

A fixture can only be compared with another fixture if its questions are of
comparable difficulty. "I think these are about right" is not a standard, so
this measures two proxies that need no model and no retrieval run:

  overlap   the share of the query's content words that also appear in the
            chunk that answers it. A drafter is SHOWN the chunk, so its
            questions inherit that chunk's wording and overlap is high. This
            is the single best predictor of whether retrieval will find it.

  length    content words per query. A very short query is under-specified;
            a very long one is doing the retrieval's work for it.

Stopwords are dropped so "how do i" does not count as overlap.
"""

from __future__ import annotations

import re
import statistics
import sys

from scripts import corpora

STOP = set(
    """a an the is are was were be been being do does did doing how what when
    where which who why to of in on for with by from at as it its this that
    these those and or not no if then than there here can could should would
    will shall may might must i you we they he she them us me my your our
    their have has had get gets got make makes made use used using does done
    into out up down over under about after before between during without
    within upon per via s t""".split()
)

WORD = re.compile(r"[a-z][a-z0-9]+")
# Identifiers must be split or the measure lies. `GenerateJsonSchema` is all
# about a json schema, and a query asking "where is the json schema generated"
# scored 0.00 against it until CamelCase and snake_case were broken apart.
SPLIT = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")


def content(text: str) -> set[str]:
    pieces = " ".join(SPLIT.findall(text))
    return {w for w in WORD.findall(pieces.lower()) if w not in STOP and len(w) > 2}


def measure(name: str) -> tuple[float, float, int] | None:
    try:
        chunks, queries = corpora.load(name)
    except SystemExit:
        return None
    by_source: dict[str, list] = {}
    for c in chunks:
        by_source.setdefault(c.source, []).append(c)

    overlaps, lengths = [], []
    for q in queries:
        found = [
            c
            for c in by_source.get(q.file, [])
            if any(c.start_line <= ln <= c.end_line for ln in q.expects)
        ]
        if not found:
            continue
        answer = content(" ".join(c.text for c in found))
        words = content(q.text)
        if not words:
            continue
        overlaps.append(len(words & answer) / len(words))
        lengths.append(len(words))
    if not overlaps:
        return None
    return statistics.mean(overlaps), statistics.mean(lengths), len(overlaps)


def per_query(name: str) -> None:
    """Every query's own overlap, so a fixture can be tuned query by query."""
    chunks, queries = corpora.load(name)
    by_source: dict[str, list] = {}
    for c in chunks:
        by_source.setdefault(c.source, []).append(c)
    for q in queries:
        found = [
            c
            for c in by_source.get(q.file, [])
            if any(c.start_line <= ln <= c.end_line for ln in q.expects)
        ]
        words = content(q.text)
        if not found or not words:
            print(f"  {q.id}  NO TARGET  {q.text[:60]}")
            continue
        answer = content(" ".join(c.text for c in found))
        ov = len(words & answer) / len(words)
        print(f"  {q.id}  {ov:.2f}  {q.text[:64]}")


def main(argv: list[str]) -> int:
    if "--per-query" in argv:
        for n in [a for a in argv[1:] if not a.startswith("--")]:
            print(f"=== {n}")
            per_query(n)
        return 0
    names = [a for a in argv[1:] if not a.startswith("--")] or sorted(corpora.SPECS)
    rows = []
    for n in names:
        got = measure(n)
        if got:
            rows.append((n, *got))
    rows.sort(key=lambda r: r[1])

    print(f"{'corpus':14}{'overlap':>9}{'words/q':>9}{'n':>5}")
    for n, ov, ln, k in rows:
        print(f"{n:14}{ov:9.3f}{ln:9.1f}{k:5}")

    drafted = [r for r in rows if not r[0].endswith("hand")]
    if drafted:
        ovs = [r[1] for r in drafted]
        m, sd = statistics.mean(ovs), statistics.pstdev(ovs)
        print(f"\nDRAFTED ZOO overlap: mean {m:.3f}  sd {sd:.3f}")
        print(f"  the comparable band (mean +/- 1 sd): {m - sd:.3f} to {m + sd:.3f}")
        for r in rows:
            if r[0].endswith("hand"):
                z = (r[1] - m) / sd if sd else 0
                verdict = (
                    "IN BAND" if abs(z) <= 1 else ("TOO HARD" if z < 0 else "TOO EASY")
                )
                print(f"  {r[0]:14} overlap {r[1]:.3f}  z={z:+.2f}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
