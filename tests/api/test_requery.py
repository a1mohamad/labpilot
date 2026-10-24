import logging
from types import SimpleNamespace

import pytest

from labpilot.agent import Claim
from labpilot.api.requery import make_query_writer
from labpilot.llm import AllFreeTiersExhausted
from labpilot.prompts import REQUERY_MAX_TOKENS

CLAIM = Claim("the time step is 0.01 s", "[paper.md · 4 Setup]", "time step is 0.01 s")


class FakeClient:
    def __init__(self, text="  dt TIME_STEP \n", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def generate(self, prompt, *, max_tokens, problem_with=None):
        self.calls.append((prompt, max_tokens, problem_with))
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text, model="fake-model", tier=3)


def test_the_new_query_is_the_text_the_model_wrote_without_its_spaces():
    new_query = make_query_writer(FakeClient())

    assert new_query(CLAIM, ("the time step is 0.01 s",), "") == "dt TIME_STEP"


def test_the_model_gets_the_claim_the_earlier_queries_the_note_and_a_token_budget():
    client = FakeClient()

    make_query_writer(client)(CLAIM, ("first words", "second words"), "about output")

    prompt, max_tokens, _ = client.calls[0]
    assert "the time step is 0.01 s" in prompt
    assert "1. first words\n2. second words" in prompt
    assert "about output" in prompt
    assert max_tokens == REQUERY_MAX_TOKENS


def test_the_client_is_told_to_reject_a_repeat_and_a_many_line_answer():
    client = FakeClient()

    make_query_writer(client)(CLAIM, ("first words",), "")

    problem_with = client.calls[0][2]
    assert problem_with(SimpleNamespace(text="new words")) is None
    assert problem_with(SimpleNamespace(text="first words")) is not None
    assert problem_with(SimpleNamespace(text="one\ntwo")) is not None


def test_when_every_tier_fails_there_is_no_new_query(caplog):
    client = FakeClient(error=AllFreeTiersExhausted(()))

    with caplog.at_level(logging.WARNING):
        query = make_query_writer(client)(CLAIM, ("first words",), "")

    assert query is None
    assert "new query" in caplog.text


def test_a_caller_bug_is_not_swallowed():
    # A claim with no text is the caller's bug, so it must crash and never be
    # hidden by the "every tier failed" rule.
    blank = Claim("   ", "[paper.md]", "x")

    with pytest.raises(ValueError):
        make_query_writer(FakeClient())(blank, ("first words",), "")


def test_the_outline_of_the_searched_file_reaches_the_writer():
    client = FakeClient()
    asked = []

    def outline(artifact_id):
        asked.append(artifact_id)
        return "B_train.py\n  def _build_stop_mask"

    sides = {"B": SimpleNamespace(artifact=SimpleNamespace(id="B-7"))}
    make_query_writer(client, outline)(CLAIM, ("first",), "", sides)

    assert asked == ["B-7"]
    assert "THE OUTLINE OF THE OTHER FILE\nB_train.py" in client.calls[0][0]


def test_with_no_stored_side_there_is_no_outline():
    client = FakeClient()

    make_query_writer(client, lambda a: "never")(CLAIM, ("first",), "", {"B": "x"})

    assert "THE OUTLINE OF THE OTHER FILE\n" not in client.calls[0][0]
