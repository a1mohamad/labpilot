"""Refuse a query fixture that cannot measure what it claims to.

    PYTHONPATH=. python scripts/validate_fixture.py cobra
    PYTHONPATH=. python scripts/validate_fixture.py --all

Six ways a retrieval fixture is silently broken. Four of them have bitten this
project already; the last two arrive with drafted fixtures.

  no target      the expected lines fall in no chunk, so the query can never be
                 answered and quietly drags every average down
  too many       a query whose answer is a third of the corpus measures nothing
  leaked         the query contains the identifier it is looking for, so the
                 run measures string matching and everything scores ~100%
  prefix bias    the categories are grouped, so a truncated run is a category
                 study wearing a corpus study's clothes
  generic        "what does this function do" is answerable by every chunk in
                 the corpus, so it scores whatever the ranker happened to put
                 first
  duplicate      the same question twice is one measurement counted twice

WHAT THIS DELIBERATELY DOES NOT CHECK: whether retrieval FINDS the answer.
Dropping the queries our embedder misses would build a fixture that agrees
with our embedder, and every later number would then be measuring the filter
rather than the method. A query has to be well FORMED here, never well
ANSWERED.
"""

from __future__ import annotations

import sys
from collections import Counter

from scripts.corpora import generic, leaked
from scripts.score_hybrid import CORPORA, targets

# A target set larger than this is not a question, it is a topic. Three chunks
# is allowed outright, because a short answer can legitimately straddle an
# overlap boundary.
MAX_TARGET_SHARE = 0.05


def check(corpus: str) -> tuple[int, dict]:
    chunks, queries = CORPORA[corpus]()
    by_source: dict[str, list] = {}
    for chunk in chunks:
        by_source.setdefault(chunk.source, []).append(chunk)

    bad = 0
    counts: list[int] = []
    seen: dict[str, str] = {}

    for query in queries:
        found = targets(chunks, query)
        counts.append(len(found))

        if not found:
            print(f"  NO TARGET   {query.id} {query.file}:{list(query.expects)}")
            if query.file not in by_source:
                print("              the file is not in the corpus at all")
            bad += 1
        elif len(found) > max(3, MAX_TARGET_SHARE * len(chunks)):
            print(f"  TOO BROAD   {query.id} matches {len(found)} chunks")
            bad += 1

        lowered = query.text.lower().strip()
        if generic(query.text):
            print(f"  GENERIC     {query.id} {query.text!r}")
            bad += 1

        if lowered in seen:
            print(f"  DUPLICATE   {query.id} repeats {seen[lowered]}")
            bad += 1
        seen[lowered] = query.id

        # The SAME rule the drafter filters with, imported rather than copied.
        # A second copy would drift, and then a fixture could pass the check
        # that built it and fail the check that judges it.
        stolen = leaked(" ".join(chunks[i].text for i in found), query.text)
        if stolen:
            print(f"  LEAKED      {query.id} -> {sorted(stolen)}")
            bad += 1

    stats = {
        "chunks": len(chunks),
        "queries": len(queries),
        "files": len(by_source),
        "targets_mean": sum(counts) / len(counts) if counts else 0,
        "asks": Counter(q.asks for q in queries),
        "wording": Counter(q.wording for q in queries),
        "bad": bad,
    }

    # Any prefix must stay a stratified sample, so a run cut short by a rate
    # limit is still a corpus result. Measured as the worst category's share of
    # the first ten: 0.2 is perfectly even over five kinds.
    first = Counter(q.asks for q in queries[:10])
    stats["prefix_skew"] = (max(first.values()) / sum(first.values())) if first else 0
    return bad, stats


def main(argv: list[str]) -> int:
    names = sorted(CORPORA) if "--all" in argv else argv[1:2]
    if not names:
        print(f"usage: {argv[0]} <corpus>|--all")
        return 2

    rows = []
    total_bad = 0
    for name in names:
        print(f"\n=== {name}")
        try:
            bad, stats = check(name)
        except SystemExit as exc:
            print(f"  SKIPPED: {exc}")
            continue
        total_bad += bad
        rows.append((name, stats))
        verdict = "OK" if not bad else f"{bad} PROBLEMS"
        print(
            f"  {stats['queries']:3} queries over {stats['chunks']:5} chunks "
            f"in {stats['files']:3} files - {verdict}"
        )

    print(
        f"\n{'corpus':12} {'chunks':>7} {'queries':>8} {'files':>6} "
        f"{'targets':>8} {'skew':>6}  kinds"
    )
    for name, s in rows:
        kinds = " ".join(f"{k[:4]}{v}" for k, v in sorted(s["asks"].items()))
        print(
            f"{name:12} {s['chunks']:7} {s['queries']:8} {s['files']:6} "
            f"{s['targets_mean']:8.1f} {s['prefix_skew']:6.2f}  {kinds}"
        )

    print(f"\n{'ALL FIXTURES OK' if not total_bad else f'{total_bad} PROBLEMS TOTAL'}")
    return 1 if total_bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
