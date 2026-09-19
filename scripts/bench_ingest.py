"""How long does an INGEST really take, at the sizes the product targets?

`WARN_MINUTES` decides whether the user is stopped and asked before an ingest
starts, and it is compared against `Ingested.embedding_minutes`. Two things
about that were never checked:

    does the ESTIMATE match the wall clock?      (it models throughput only)
    at what chunk count does the threshold fire? (nobody measured the curve)

H19 answered neither: it timed two artifacts of 18 and 82 chunks, both far
below the 1,000-10,000 range this product targets, and then reasoned about
10,000-chunk repositories from them.

    PYTHONPATH=. python scripts/bench_ingest.py

Costs EMBEDDER quota and no generation quota. It drives the real
`ingest_source`, so it measures chunking, embedding, batching and the write
transaction together - which is what the user actually waits through, and what
the estimate is supposed to predict.
"""

from __future__ import annotations

import os
import time

from dotenv import load_dotenv

from labpilot.api import services
from labpilot.embed.registry import MIGRATION
from labpilot.sources import open_folder
from labpilot.store import connect
from labpilot.tokens import estimate_tokens

# Smallest first, so a failure part way through still leaves a usable curve.
CORPORA = [
    ("websocket", "LABPILOT_WEBSOCKET_SRC"),
    ("log", "LABPILOT_LOG_SRC"),
    ("cobra", "LABPILOT_COBRA_SRC"),
    ("requests", "LABPILOT_REQUESTS_SRC"),
    ("geo", "LABPILOT_GEO_SRC"),
    ("zod", "LABPILOT_ZOD_SRC"),
]


def main() -> int:
    load_dotenv(".env")
    codestral = MIGRATION[0]
    rows = []

    with connect() as conn:
        print(
            f"{'corpus':12}{'chunks':>8}{'MEASURED':>11}{'PREDICTED':>11}{'ratio':>8}"
        )
        for name, env in CORPORA:
            root = os.getenv(env)
            if not root:
                print(f"{name:12}{env} unset, skipped")
                continue
            try:
                with open_folder(root, name=name) as source:
                    start = time.perf_counter()
                    got = services.ingest_source(conn, source, side="B")
                    measured = time.perf_counter() - start
            except Exception as exc:  # noqa: BLE001 - a failure IS a result here
                print(f"{name:12}FAILED: {str(exc)[:70]}")
                continue

            # What the estimate WOULD have said, on the same chunks. Chunked
            # again OUTSIDE the timer on purpose: the measured span has to be
            # the whole ingest the user waits through, chunking included, and
            # counting tokens inside it would charge that work twice.
            with open_folder(root, name=name) as again:
                tokens = sum(
                    estimate_tokens(c.embed_text)
                    for c in services.chunk_source(again, side="B")
                )
            predicted = (
                codestral.embedding_minutes(tokens=tokens, chunks=got.chunks) * 60
            )
            rows.append((name, got.chunks, measured, predicted))
            print(
                f"{name:12}{got.chunks:>8}{measured:>10.1f}s{predicted:>10.1f}s"
                f"{measured / predicted if predicted else 0:>7.1f}x"
            )

    if len(rows) >= 2:
        # A straight line through the two ends is enough to say where the
        # threshold falls. Anything fancier would over-read six points.
        first, last = rows[0], rows[-1]
        per_chunk = (last[2] - first[2]) / (last[1] - first[1])
        fixed = first[2] - per_chunk * first[1]
        print(f"\nmeasured ingest ~ {fixed:.1f}s + {per_chunk:.3f}s per chunk")
        for n in (1_000, 5_000, 10_000):
            print(f"  {n:>6,} chunks -> {(fixed + per_chunk * n) / 60:>6.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
