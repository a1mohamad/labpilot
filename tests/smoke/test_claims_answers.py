"""THE REAL CLAIMS, CHECK AND NEW-QUERY STEPS, ON STORED FILES, WITH A REAL MODEL.

Slice 7 added three model calls: the claims and the check of one claim are
answered through a TOOL (the model "calls" a function and its arguments are the
answer), and the new query is plain text. Every part of them was proven with a
fake provider, plus one live look on 2026-10-24. A tier that stops honouring
tools, or a prompt that stops giving parts the code can read, would first show
up as a report with no findings and no error, because a failed claims step is
only logged (D65).

WHAT THIS SPENDS, per run: two ingests of embedder quota (a paper and a code
file), ONE query embed, and three generation calls on the claims chain, which
starts with Flash-Lite. It needs a live Postgres, so it carries both gates.

WHAT IT CHECKS: claims come back, each with its quote and its place; one claim
is checked against what a search found and the verdict is one of the three we
read; a new query is one short line. It does NOT check that the claims or the
verdict are good. That is what the measurements of slices 7 and 13 are for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.agent.check_one import EVIDENCE_PARTS
from labpilot.agent.check_schema import VERDICTS
from labpilot.api import ingestion, reading, searching
from labpilot.api.chains import for_claims
from labpilot.api.checking import make_checker
from labpilot.api.claims import make_claims_extractor
from labpilot.api.requery import make_query_writer
from labpilot.llm import LLMClient
from labpilot.prompts import MAX_QUERY_CHARS

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")
QUESTION = "Compare these and explain why the results diverge."


@pytest.mark.smoke
def test_claims_a_check_and_a_new_query_work_on_stored_files(db):
    paper = ingestion.ingest_artifact(
        db, (SAMPLES / "A_paper.md").read_bytes(), name="A_paper.md", side="A"
    )
    code = ingestion.ingest_artifact(
        db, (SAMPLES / "B_train.py").read_bytes(), name="B_train.py", side="B"
    )
    client = for_claims(LLMClient())

    claims = make_claims_extractor(db, client)(paper.artifact.id)

    assert claims, "a claims step that gives nothing is a failed tier, not an answer"
    assert all(claim.text and claim.source and claim.quote for claim in claims)

    sides = reading.measure_sides(db, paper.artifact.id, code.artifact.id)
    evidence = searching.retrieve_query(db, sides, side="B", text=claims[0].text)
    evidence = evidence[:EVIDENCE_PARTS]
    assert evidence, "the stored code must give the search something to find"

    finding = make_checker(client)(claims[0], evidence)

    print(finding)

    assert finding.verdict in VERDICTS
    if finding.verdict != "absent":
        assert finding.source and finding.quote

    query = make_query_writer(client)(
        claims[0], (claims[0].text,), "the parts do not show it"
    )

    print(query)

    assert query, "no tier wrote a new query"
    assert "\n" not in query
    assert len(query) <= MAX_QUERY_CHARS
