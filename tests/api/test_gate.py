import pytest

from labpilot.agent import Correspondence, GateError
from labpilot.api.gate import HALT_MODEL, halt_answer, make_gate
from labpilot.llm import AllFreeTiersExhausted, Attempt, LLMResult
from labpilot.prompts import GATE_MAX_TOKENS

GOOD = {"verdict": "NONE", "reason": "one is about memory, one about images"}


class FakeClient:
    def __init__(self, arguments=None, error=None):
        self.arguments = arguments
        self.error = error
        self.calls = []
        self.hooks = []

    def generate(self, prompt, *, max_tokens, tool=None, problem_with=None):
        self.calls.append((prompt, max_tokens, tool))
        self.hooks.append(problem_with)
        if self.error:
            raise self.error
        return LLMResult(
            text="{}", model="fake-model", tier=1, arguments=self.arguments
        )


def test_the_verdict_comes_back_as_a_correspondence():
    gate = make_gate(FakeClient(GOOD))

    assert gate("about memory", "about images") == Correspondence(
        "NONE", "one is about memory, one about images"
    )


def test_the_model_gets_the_prompt_the_budget_and_the_forced_tool():
    client = FakeClient(GOOD)

    make_gate(client)("about memory", "about images")

    prompt, max_tokens, tool = client.calls[0]
    assert "about memory" in prompt and "about images" in prompt
    assert max_tokens == GATE_MAX_TOKENS
    assert tool.name == "judge_correspondence"
    assert tool.parameters["required"] == ["verdict", "reason"]


def test_a_wrong_answer_is_sent_back_to_the_chain_by_the_problem_hook():
    client = FakeClient(GOOD)
    make_gate(client)("a", "b")
    hook = client.hooks[0]

    def result(arguments):
        return LLMResult(text="", model="m", tier=1, arguments=arguments)

    assert hook(result(GOOD)) is None
    assert "no arguments" in hook(result(None))
    assert "verdict" in hook(result({"verdict": "MAYBE", "reason": "x"}))
    assert "reason" in hook(result({"verdict": "NONE", "reason": " "}))


def test_when_every_tier_fails_the_error_is_the_gates_own():
    error = AllFreeTiersExhausted([Attempt(1, "m", "HTTP 429")])

    with pytest.raises(GateError, match="no tier"):
        make_gate(FakeClient(error=error))("a", "b")


def test_an_answer_with_no_arguments_is_a_gate_error():
    with pytest.raises(GateError, match="no arguments"):
        make_gate(FakeClient(None))("a", "b")


def test_the_halt_answer_holds_the_reason_and_both_summaries():
    result = halt_answer("about memory", "about images", "they differ")

    assert "they differ" in result.text
    assert "A: about memory" in result.text
    assert "B: about images" in result.text
    assert result.text.index("A: about memory") < result.text.index("B: about images")


def test_the_halt_answer_says_who_wrote_it_and_that_it_finished():
    result = halt_answer("a", "b", "c")

    assert result.model == "correspondence gate"
    assert result.model == HALT_MODEL
    assert result.tier == 0
    assert result.finish_reason == "stop"
    assert result.attempts == ()
