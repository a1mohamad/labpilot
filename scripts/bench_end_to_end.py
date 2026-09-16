"""What does one whole answer actually cost in wall clock?

Slice 8 job 4, and it had never been measured. The project has per-stage
numbers - 34 ms for search, 1.3 s for a rerank call, 52.7 s for a report -
and no total, so `WARN_MINUTES = 2.0` and `EMBEDDING_MINUTES_BUDGET = 6.0`
are both guesses that CLAUDE.md labels as guesses.

    PYTHONPATH=. python scripts/bench_end_to_end.py

It drives the REAL ask path - `services.ask()` - so it measures what we
ship, including the rerank chain assembled at the entry layer and the real
generator chain with its fallbacks. Two shapes are timed, because they are
different products:

    STUFF    both artifacts fit the prompt budget, so no embed, no search,
             no rerank. The cheapest an answer can be.
    SEARCH   side B is a repository, so the whole ladder runs.

Ingest is timed separately and once, because it happens once per artifact
and everything after it happens per question.
"""

from __future__ import annotations

import time
from pathlib import Path

from dotenv import load_dotenv

from labpilot.api import services
from labpilot.llm import CHAIN, LLMClient
from labpilot.store import connect

SAMPLES = Path("data/samples/quora_siamese")
QUESTION = "Compare these and explain why the results diverge."


class Timed:
    """Wrap the pieces `ask()` calls so each stage reports its own seconds.

    Patching the module attributes rather than editing `services` keeps the
    measurement outside the thing being measured - the same reason the
    scoring scripts live in `scripts/` and not in `labpilot/`.
    """

    def __init__(self) -> None:
        self.spans: dict[str, float] = {}

    def wrap(self, name: str, fn):
        def inner(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                self.spans[name] = self.spans.get(name, 0.0) + (
                    time.perf_counter() - start
                )

        return inner


def ingest(conn, path: Path, side: str) -> tuple[str, float, int]:
    raw = path.read_bytes()
    start = time.perf_counter()
    got = services.ingest_artifact(conn, raw, name=path.name, side=side)
    return got.artifact.id, time.perf_counter() - start, got.chunks


def main() -> int:
    load_dotenv(".env")
    client = LLMClient(chain=CHAIN)

    with connect() as conn:
        print("INGEST - once per artifact")
        a_id, a_secs, a_chunks = ingest(conn, SAMPLES / "A_paper.md", "A")
        print(f"  A_paper.md   {a_chunks:>5} chunks  {a_secs:>7.1f}s")
        b_id, b_secs, b_chunks = ingest(conn, SAMPLES / "B_train.py", "B")
        print(f"  B_train.py   {b_chunks:>5} chunks  {b_secs:>7.1f}s")

        for label, pair in (
            ("STUFF  (paper + one file)", (a_id, b_id)),
            ("SEARCH (paper + 729-chunk Go repo)", (a_id, "B-bench-geo")),
        ):
            timer = Timed()
            originals = {
                name: getattr(services, name)
                for name in ("_embed_question", "search", "_best", "_prompt")
            }
            for name, fn in originals.items():
                setattr(services, name, timer.wrap(name, fn))
            try:
                start = time.perf_counter()
                out = services.ask(
                    conn, pair[0], pair[1], question=QUESTION, client=client
                )
                total = time.perf_counter() - start
            except Exception as exc:  # noqa: BLE001 - a failure IS a result here
                print(f"\n{label}\n  FAILED: {str(exc)[:200]}")
                continue
            finally:
                for name, fn in originals.items():
                    setattr(services, name, fn)

            stages = dict(timer.spans)
            generate = total - sum(stages.values())
            print(f"\n{label}")
            print(f"  served by       {out.result.model} (tier {out.result.tier})")
            print(f"  chunks sent     {len(out.selected)} of {len(out.chunks)}")
            for name in ("_embed_question", "search", "_best", "_prompt"):
                secs = stages.get(name, 0.0)
                print(f"  {name:<16}{secs:>8.2f}s{secs / total * 100:>7.1f}%")
            print(f"  {'generate':<16}{generate:>8.2f}s{generate / total * 100:>7.1f}%")
            print(f"  {'TOTAL':<16}{total:>8.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
