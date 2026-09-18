"""Would excluding tests / docs / config actually help? Free, over cached vectors.

The instinct is that a real repository's tests and docs are noise competing with
the source. That is an ASSUMPTION, and it is cheap to check: drop each kind from
the corpus the real walk builds and re-score the same queries.

It also has a counter-example already: `pytest` - a corpus that is almost
entirely tests - lost 0.004 MRR on the real walk. If tests were noise, the
corpus made mostly of them should have been the worst.

No embedding: every vector is cached, and dropping chunks only removes rows.
"""

from __future__ import annotations

import re

from dotenv import load_dotenv

from scripts import corpora
from scripts.score_hybrid import EMBEDDERS, embedded, targets
from scripts.score_real_ingest import real_chunks

TEST = re.compile(r"(^|/)(tests?|testing|spec|specs)(/|$)|(^|/)(test_|conftest)")
DOC = re.compile(r"\.(md|markdown|rst|txt)$|(^|/)(docs?|documentation)(/|$)")
CONFIG = re.compile(r"\.(ya?ml|toml|ini|cfg|json)$|(^|/)\.github(/|$)")


def kind(path: str) -> str:
    if TEST.search(path):
        return "test"
    if DOC.search(path):
        return "doc"
    if CONFIG.search(path):
        return "config"
    return "source"


def score(chunks, vectors, queries, qv) -> tuple[float, float, int]:
    places = []
    for i, q in enumerate(queries):
        want = targets(chunks, q)
        if not want:
            continue
        order = sorted(
            range(len(chunks)),
            key=lambda j: -sum(a * b for a, b in zip(vectors[j], qv[i], strict=True)),
        )
        places.append(
            next((r for r, j in enumerate(order, 1) if j in want), len(chunks) + 1)
        )
    mrr = sum(1 / p for p in places) / len(places)
    r10 = sum(p <= 10 for p in places) / len(places)
    return mrr, r10, len(places)


def main() -> None:
    load_dotenv()
    e = EMBEDDERS["codestral"]
    for name in ("smsspam", "disaster", "click", "pytest"):
        narrow, queries = corpora.load(name)
        real, _ = real_chunks(name)
        tag = f"{name}_{e.model}"
        qv = embedded(e, [q.text for q in queries], task="query", tag=f"{tag}_queries")
        rv = embedded(
            e, [c.embed_text for c in real], task="document", tag=f"{tag}_realingest"
        )
        if len(rv) != len(real):
            print(f"{name}: cache {len(rv)} vs {len(real)} chunks - SKIPPED\n")
            continue

        kinds = [kind(c.source) for c in real]
        mix = {k: kinds.count(k) for k in ("source", "test", "doc", "config")}
        print(f"=== {name}: {len(real)} chunks  {mix}")

        base = score(real, rv, queries, qv)
        print(f"  {'everything':22}{base[0]:8.3f}{base[1]:8.3f}   n={base[2]}")

        for drop in ("test", "doc", "config"):
            keep = [i for i, k in enumerate(kinds) if k != drop]
            if len(keep) == len(real):
                continue
            sub = [real[i] for i in keep]
            sv = [rv[i] for i in keep]
            m, r, n = score(sub, sv, queries, qv)
            flag = "" if n == base[2] else f"   <- {base[2] - n} QUERIES LOST"
            print(
                f"  {'without ' + drop:22}{m:8.3f}{r:8.3f}   "
                f"{m - base[0]:+.3f}  {len(real) - len(sub)} chunks{flag}"
            )
        print()


if __name__ == "__main__":
    main()
