"""THE WEEKLY RUN, AGAINST THE PATH WE ACTUALLY SHIP.

Until 2026-09-19 the only pipeline smoke test drove `chunk_file` -> `select` ->
`build_prompt` -> `LLMClient`. That pipeline was replaced in slice 7 and has
not been the product since: today a question goes

    ingest_artifact  ->  Postgres  ->  ask()  ->  measure, fits?
                                                  embed the question
                                                  search per side
                                                  the gate
                                                  the rerank CHAIN
                                                  select -> prompt -> generate

So the weekly liveness check was watching a building we had moved out of. Four
whole layers - the store, the ask ladder, the assembled rerank chain and both
doors - had no live coverage at all, and the one thing smoke exists to tell us
is that a free provider died in the night.

WHAT THIS SPENDS, per run: 2 ingests of embedder quota, 2 query embeds, one
rerank call PER SIDE on the live chain (flash-lite leads it, 500/day across two
keys), and ONE generation. It needs a live Postgres as well, so it carries the
cost of both gates and skips when either is absent.

WHY THE SEARCH PATH AND NOT THE STUFF PATH: `A_paper.md` + `B_train.py` is
28,246 tokens against a PROMPT_BUDGET of 26,000, so `_fits` refuses and the
whole ladder runs. Stuffing would exercise measure, read_chunks and generate
and skip everything in between.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.api import services
from labpilot.llm import LLMClient
from labpilot.prompts import find_citations, resolve
from labpilot.store import read_chunks

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")
ARTIFACTS = Path("artifacts")
QUESTION = "Compare these and explain why the results diverge."


@pytest.mark.smoke
def test_a_stored_pair_answers_through_the_shipped_ask_path(db):
    a = services.ingest_artifact(
        db, (SAMPLES / "A_paper.md").read_bytes(), name="A_paper.md", side="A"
    )
    b = services.ingest_artifact(
        db, (SAMPLES / "B_train.py").read_bytes(), name="B_train.py", side="B"
    )

    assert a.chunks and b.chunks, "premise: both artifacts must really be stored"

    out = services.ask(
        db, a.artifact.id, b.artifact.id, question=QUESTION, client=LLMClient()
    )

    assert out.result.text

    # WHICH PATH RAN, asserted rather than assumed. `totals` is None only when
    # the corpus was stuffed, and a stuffed run skips every stage this test
    # exists to exercise - so a None here means the fixture grew, or the budget
    # moved, and the run proved far less than its name claims.
    assert out.totals is not None, (
        "this pair must SEARCH. It stuffed instead, so the embed, search, gate "
        "and rerank stages did not run and this test checked almost nothing"
    )
    assert len(out.selected) < sum(out.totals.values())

    _report(a, b, out)


@pytest.mark.smoke
def test_a_real_citation_survives_the_round_trip_to_postgres(db):
    """The one end-to-end honesty check, and it needs a REAL model to be real.

    A citation is `[B-17 "some exact line"]`. Resolving it walks:

        the model's quote -> the chunk we showed it -> chunk.start_line
            -> a line number in the user's file

    Every step is ours except the first, and each one can be off by one without
    raising: a header dropped on the way into Postgres, a `start_line` shifted
    by the writer, a rerank POSITION read as a chunk id. The integration suite
    pins this with a stubbed model, which proves the arithmetic; only a live
    model proves it against text a model actually chose to quote.

    It asserts a RATE rather than perfection: a model may quote a line it
    reworded, and that is the model's miss, not ours.
    """
    a = services.ingest_artifact(
        db, (SAMPLES / "A_paper.md").read_bytes(), name="A_paper.md", side="A"
    )
    b = services.ingest_artifact(
        db, (SAMPLES / "B_train.py").read_bytes(), name="B_train.py", side="B"
    )
    out = services.ask(
        db, a.artifact.id, b.artifact.id, question=QUESTION, client=LLMClient()
    )

    cited = find_citations(out.result.text)
    assert cited, "a report with no citations cannot be checked at all"

    landed = [
        found
        for chunk_id, quote in cited
        if (found := resolve(chunk_id, quote, out.chunks))
    ]
    assert len(landed) >= len(cited) * 0.5, (
        f"only {len(landed)} of {len(cited)} citations resolved. Under half "
        f"means the ids or the line numbers moved, not that the model guessed"
    )

    # And the resolved line must be the line that is really in the user's file.
    # `resolve` reads our COPY; this reads the original from disk, so a header
    # or an offset lost on the way through Postgres shows up here and nowhere
    # else.
    for citation in landed:
        lines = (SAMPLES / citation.source).read_text(encoding="utf-8").splitlines()
        assert lines[citation.line - 1] == citation.text, (
            f"{citation.source}:{citation.line} holds "
            f"{lines[citation.line - 1]!r}, but we told the user it holds "
            f"{citation.text!r}. The chunk's start_line did not survive storage"
        )

    # The stored corpus is what was searched, so a side that came back empty
    # would make every number above meaningless.
    assert read_chunks(db, b.artifact.id)


def _report(a, b, out) -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    model = out.result.model.replace("/", "-")
    path = ARTIFACTS / f"{stamp}_ask_{model}.md"

    cited = find_citations(out.result.text)
    landed = [pair for pair in cited if resolve(pair[0], pair[1], out.chunks)]
    sent = {side: 0 for side in out.totals}
    for chunk in out.selected:
        sent[chunk.side] = sent.get(chunk.side, 0) + 1

    path.write_text(
        f"# ask() · {out.result.model} (tier {out.result.tier})\n\n"
        f"- finish reason: {out.result.finish_reason}\n"
        f"- ingested: A {a.chunks} chunks, B {b.chunks} chunks\n"
        f"- sent per side: {sent} of {out.totals}\n"
        f"- citations written: {len(cited)}\n"
        f"- citations that resolve: {len(landed)}\n"
        f"- failed tiers: {[at.model for at in out.result.attempts] or 'none'}\n\n"
        f"## Answer\n\n{out.result.text}\n\n"
        f"## Prompt that produced it\n\n{out.prompt}\n",
        encoding="utf-8",
    )
    print(f"\nsaved -> {path}")
