import pytest

from labpilot.api.answering import answerer, generate
from labpilot.api.errors import GenerationUnavailable
from labpilot.llm import AllFreeTiersExhausted, Attempt, LLMResult, routes


class FakeClient:
    chain = ()

    def __init__(self, error=None):
        self.error = error
        self.asked = []

    def generate(self, prompt, *, max_tokens):
        self.asked.append((prompt, max_tokens))
        if self.error:
            raise self.error
        return LLMResult(text="the answer", model="m", tier=1)


def test_the_answer_of_a_model_comes_back():
    client = FakeClient()

    assert generate(client, "prompt", max_tokens=7).text == "the answer"
    assert client.asked == [("prompt", 7)]


def test_when_every_tier_fails_the_api_error_carries_the_attempts():
    attempts = [Attempt(1, "m", "HTTP 429")]

    with pytest.raises(GenerationUnavailable) as caught:
        generate(FakeClient(AllFreeTiersExhausted(attempts)), "p", max_tokens=7)

    assert caught.value.attempts == attempts


@pytest.mark.parametrize(
    ("files", "task"),
    [(0, "respond_chat"), (1, "respond_one"), (2, "respond_two"), (3, "respond_two")],
)
def test_each_number_of_files_asks_for_its_own_number_of_tokens(
    monkeypatch, files, task
):
    from labpilot.api import answering

    client = FakeClient()
    monkeypatch.setattr(answering, "for_task", lambda given, name: client)

    answerer(client, files)("prompt")

    assert client.asked == [("prompt", routes.TASKS[task].max_tokens)]
