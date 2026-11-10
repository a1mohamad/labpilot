import logging
from types import SimpleNamespace

import pytest

from labpilot.api.followups import last_answer_text, make_rewriter
from labpilot.llm import AllFreeTiersExhausted
from labpilot.prompts import FOLLOW_UP_MAX_TOKENS, KEPT_ANSWER_CHARS


class FakeClient:
    def __init__(self, text="what is the learning rate in A and B?", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def generate(self, prompt, *, max_tokens, problem_with=None):
        self.calls.append((prompt, max_tokens, problem_with))
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text, model="fake-model", tier=3)


def test_the_rewrite_is_the_text_the_model_wrote():
    rewrite = make_rewriter(FakeClient())

    rewritten = rewrite("and the lr?", ["why?"], "")

    assert rewritten == "what is the learning rate in A and B?"


def test_the_model_gets_the_questions_the_last_answer_and_a_token_budget():
    client = FakeClient()

    make_rewriter(client)("do the second one", ["what can I improve?"], "1. a 2. b")

    prompt, max_tokens, _ = client.calls[0]
    assert "what can I improve?" in prompt
    assert "do the second one" in prompt
    assert "1. a 2. b" in prompt
    assert max_tokens == FOLLOW_UP_MAX_TOKENS


def test_the_client_is_told_to_reject_a_blank_or_many_line_answer():
    client = FakeClient()

    make_rewriter(client)("and the lr?", ["why?"], "")

    problem_with = client.calls[0][2]
    assert problem_with(SimpleNamespace(text="one good line?")) is None
    assert problem_with(SimpleNamespace(text="line one\nline two")) is not None


def test_when_every_tier_fails_the_question_goes_on_as_it_was(caplog):
    client = FakeClient(error=AllFreeTiersExhausted(()))

    with caplog.at_level(logging.WARNING):
        rewritten = make_rewriter(client)("and the lr?", ["why?"], "an answer")

    assert rewritten == "and the lr?"
    assert "rewrite" in caplog.text


def test_a_caller_bug_is_not_swallowed():
    # An empty question is the caller's bug, so it must crash and never be
    # hidden by the "every tier failed" rule.
    with pytest.raises(ValueError):
        make_rewriter(FakeClient())("   ", ["why?"], "")


def test_the_saved_last_answer_is_the_whole_answer_up_to_its_cap():
    # D104: a follow-up such as "fix bug 3" needs the part that names bug 3, so
    # the chat keeps the whole answer, cut only past KEPT_ANSWER_CHARS.
    short = SimpleNamespace(text="  a short answer  ")
    report = SimpleNamespace(text="the start " + "x" * 12_000 + "the end")
    huge = SimpleNamespace(text="x" * (KEPT_ANSWER_CHARS + 500) + "the end")

    assert last_answer_text(short) == "a short answer"
    assert last_answer_text(report) == report.text
    assert len(last_answer_text(huge)) == KEPT_ANSWER_CHARS
    assert last_answer_text(huge).endswith("the end")
