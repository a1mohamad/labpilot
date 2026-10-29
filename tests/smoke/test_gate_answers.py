"""THE REAL GATE, WITH A REAL MODEL, ON TWO SHORT SUMMARIES.

WHAT THIS SPENDS: two generation calls on the claims chain (Flash-Lite first).
It needs no database. It checks that the verdict is one of the three we read and
that plainly different summaries get NONE. It does NOT measure the gate: that is
M28, with real summaries, at the end of the slice.
"""

from __future__ import annotations

import pytest
from dotenv import load_dotenv

from labpilot.agent import GATE_VERDICTS, HALT_VERDICT
from labpilot.api.chains import for_claims
from labpilot.api.gate import make_gate
from labpilot.llm import LLMClient

load_dotenv()

PAPER = (
    "A paper that studies whether two short questions ask the same thing. It "
    "encodes each question with a recurrent network and an attention layer, "
    "compares the two encodings, and reports an F1 score on a public set of "
    "question pairs."
)
CODE = (
    "A training script that builds a recurrent network with attention to decide "
    "whether two questions are duplicates. It trains on question pairs, tunes a "
    "threshold on a validation split and prints an F1 score."
)
OTHER = (
    "A library that sends web requests. It builds a request, handles redirects, "
    "keeps cookies in a session and returns the response body and its headers."
)


@pytest.mark.smoke
def test_the_gate_gives_a_readable_verdict_and_halts_only_on_a_clear_mismatch():
    gate = make_gate(for_claims(LLMClient()))

    same = gate(PAPER, CODE)
    different = gate(PAPER, OTHER)

    print(same)
    print(different)

    assert same.verdict in GATE_VERDICTS and same.reason
    assert same.verdict != HALT_VERDICT
    assert different.verdict == HALT_VERDICT and different.reason
