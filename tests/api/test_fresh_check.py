"""The new check of a fresh question: one statement, one audit, one saved result."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from labpilot.agent import Difference, DifferencesError
from labpilot.api import fresh as fresh_module
from labpilot.api import saved as saved_module
from labpilot.api.fresh import make_fresh_check
from labpilot.api.saved import SavedResults, fresh_key, saved_fresh
from labpilot.ingest import Chunk
from labpilot.llm import AllFreeTiersExhausted
from labpilot.prompts import FRESH_VERSION, build_fresh_claim_prompt

EVIDENCE = Chunk(
    text="def step(): ...",
    source="adam.py",
    start_line=1,
    end_line=2,
    side="B",
    artifact_id="B-1",
    chunk_index=3,
)
FOUND = Difference(
    "missing", "B never clips", "[adam.py]", "def step", fact="the code clips"
)


class Parts:
    def chunk_for(self, source):
        return EVIDENCE if source == "[adam.py]" else None


class Small:
    def __init__(self, text="The code clips the gradient norm."):
        self.text, self.prompts = text, []

    def generate(self, prompt, *, max_tokens):
        self.prompts.append(prompt)
        return SimpleNamespace(text=self.text)


@pytest.fixture
def audited(monkeypatch):
    seen = {"result": ([FOUND], True)}
    monkeypatch.setattr(
        fresh_module, "read_parts", lambda conn, b, *, limit, error: Parts()
    )

    def run_audit(client, facts, b):
        seen["facts"] = list(facts)
        return seen["result"]

    monkeypatch.setattr(fresh_module, "run_audit", run_audit)
    return seen


def test_the_question_becomes_one_statement_and_the_audit_checks_it(audited):
    small = Small()

    found = make_fresh_check("conn", whole=object(), small=small)(
        "Does the code clip the gradient norm?", "B-1"
    )

    assert "Does the code clip the gradient norm?" in small.prompts[0]
    assert audited["facts"] == ["The code clips the gradient norm."]
    assert len(found) == 1


def test_the_finding_is_not_a_fact_of_a_and_carries_its_evidence(audited):
    (found,) = make_fresh_check("conn", whole=object(), small=Small())("Q?", "B-1")

    assert found.fact == ""
    assert found.text.startswith('Asked "Q?":')
    assert found.evidence == EVIDENCE


def test_a_code_that_does_what_the_question_says_gives_no_finding(audited):
    audited["result"] = ([], True)

    assert make_fresh_check("conn", whole=object(), small=Small())("Q?", "B-1") == ()


def test_no_answer_from_the_audit_is_an_error_not_a_yes(audited):
    audited["result"] = ([], False)

    with pytest.raises(DifferencesError):
        make_fresh_check("conn", whole=object(), small=Small())("Q?", "B-1")


def test_no_tier_for_the_statement_is_an_error(audited):
    class Down:
        def generate(self, prompt, *, max_tokens):
            raise AllFreeTiersExhausted([])

    with pytest.raises(DifferencesError):
        make_fresh_check("conn", whole=object(), small=Down())("Q?", "B-1")


def test_an_empty_statement_is_an_error(audited):
    with pytest.raises(DifferencesError):
        make_fresh_check("conn", whole=object(), small=Small(text="  "))("Q?", "B-1")


def test_the_statement_prompt_says_to_write_only_the_statement():
    assert "Write only the statement" in build_fresh_claim_prompt("Q?")


# ---- saving ---------------------------------------------------------------


@pytest.fixture
def store(monkeypatch):
    rows = {}

    def read(conn, key):
        row = rows.get(key)
        return None if row is None else (row[0], row[1])

    def write(conn, key, kind, payload, *, artifacts):
        rows[key] = (kind, payload, artifacts)

    monkeypatch.setattr(saved_module, "read_saved", read)
    monkeypatch.setattr(saved_module, "write_saved", write)
    return rows


def test_the_same_question_about_the_same_file_is_checked_once(store):
    calls = []

    def check(question, b):
        calls.append(question)
        return (FOUND,)

    first = saved_fresh(SavedResults("conn"), check)("Does it clip?", "B-1")
    second = saved_fresh(SavedResults("conn"), check)("  does it clip?  ", "B-1")

    assert first == second == (FOUND,)
    assert calls == ["Does it clip?"]


def test_another_question_or_another_file_is_a_new_check(store):
    calls = []

    def check(question, b):
        calls.append((question, b))
        return ()

    fresh = saved_fresh(SavedResults("conn"), check)
    fresh("Does it clip?", "B-1")
    fresh("Does it log?", "B-1")
    fresh("Does it clip?", "B-2")

    assert len(calls) == 3


def test_the_key_names_the_file_the_versions_and_the_question():
    key = fresh_key("B-1", "Does it clip?")

    assert key.startswith("fresh:B-1:")
    assert f"f{FRESH_VERSION}" in key
    assert key != fresh_key("B-1", "Does it log?")
