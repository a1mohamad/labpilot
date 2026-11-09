"""THE REAL CLAIMS, DIFFERENCES AND BUGS STEPS, ON STORED FILES, WITH A REAL MODEL.

Slice 9 answers every step through a TOOL (the model "calls" a function and its
arguments are the answer). Every part was proven with a fake provider. A tier
that stops honouring tools, or a prompt that stops giving parts the code can
read, would first show up as a report with no findings and no error, because a
failed finder is only logged.

WHAT THIS SPENDS, per run: two ingests of embedder quota (a paper and a code
file), the claims (a few Flash-Lite calls), the differences (about 8 calls: the
audit, the scan, the judge and the merge) and the bugs (about 16 calls on the
full chain). It needs a live Postgres, so it carries both gates.

WHAT IT CHECKS: claims come back with their quotes; the differences and the
bugs come back placed in B (a source and a quote that is in that part). It does
NOT check that they are good. That is what the measurements of slices 9 and 13
are for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import load_dotenv

from labpilot.agent import DIFFERS, METHOD, MISSING, SILENT
from labpilot.api import ingestion
from labpilot.api.bugs import make_bug_finder
from labpilot.api.chains import for_claims, for_skeptic, for_trace
from labpilot.api.claims import make_claims_extractor
from labpilot.api.difference_finder import make_find_differences
from labpilot.api.difference_review import make_merger
from labpilot.llm import LLMClient

load_dotenv()

SAMPLES = Path("data/samples/quora_siamese")


@pytest.mark.smoke
def test_claims_differences_and_bugs_work_on_stored_files(db):
    paper = ingestion.ingest_artifact(
        db, (SAMPLES / "A_paper.md").read_bytes(), name="A_paper.md", side="A"
    )
    code = ingestion.ingest_artifact(
        db, (SAMPLES / "B_train.py").read_bytes(), name="B_train.py", side="B"
    )
    client = LLMClient()
    cheap = for_claims(client)

    claims = make_claims_extractor(db, cheap)(paper.artifact.id)

    assert claims, "a claims step that gives nothing is a failed tier, not an answer"
    assert all(claim.text and claim.source and claim.quote for claim in claims)

    facts = [claim.text for claim in claims if claim.kind == METHOD]
    find = make_find_differences(db, whole=cheap, small=cheap, merge=make_merger(cheap))
    differences = find(paper.artifact.id, code.artifact.id, facts)

    print(*differences, sep="\n")

    assert differences, "the sample pair has known differences"
    assert all(found.kind in (DIFFERS, MISSING, SILENT) for found in differences)
    assert all(found.source and found.evidence for found in differences if found.quote)

    bugs = make_bug_finder(
        db,
        client=client,
        skeptic_client=for_skeptic(client),
        trace_client=for_trace(client),
    )(code.artifact.id, "")

    print(*bugs, sep="\n")

    assert bugs, "the sample code has known defects"
    assert all(bug.source and bug.quote for bug in bugs)
