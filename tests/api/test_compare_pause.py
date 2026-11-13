"""POST /compare when the run pauses to ask the person one question (D109).

The door only: `ask` is replaced, so these check the reply SHAPE and that the
person's reply travels on. The pause itself is tested in
tests/unit/agent/test_ask_user.py and against the real saver in
tests/integration/test_ask_user_saved.py.
"""

from __future__ import annotations

import contextlib

import pytest

from labpilot.api.config import ApiConfig
from labpilot.api.contracts import Comparison, Question
from labpilot.llm import LLMResult

COMPARE = f"{ApiConfig.PREFIX}/compare"
BODY = {"a": "A-paper", "b": "B-code", "question": "why is my F1 lower?"}


class Calls(list):
    """The calls `ask` received, and the answers it will give, in order."""

    def __init__(self):
        super().__init__()
        self.outcomes: list = []


@pytest.fixture
def seen(monkeypatch):
    """Replace the database and `ask`; return the calls `ask` received."""
    monkeypatch.setattr(
        "labpilot.api.routers.compare.connect",
        lambda *a, **k: contextlib.nullcontext(object()),
    )
    calls = Calls()

    def fake_ask(conn, a_id, b_id, **kwargs):
        calls.append(kwargs)
        return calls.outcomes.pop(0)

    monkeypatch.setattr("labpilot.api.asking.ask", fake_ask)
    return calls


def answered() -> Comparison:
    return Comparison(
        result=LLMResult(text="the report", model="m", tier=1, finish_reason="STOP"),
        chunks=(),
        selected=(),
        prompt="p",
    )


def test_a_paused_run_answers_with_a_question_and_the_chat_id(client, seen):
    seen.outcomes.append(Question(text="What F1 did you get?"))

    response = client.post(COMPARE, json=BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "question"
    assert body["question"] == "What F1 did you get?"
    assert body["thread_id"]
    assert "answer" not in body


def test_a_normal_report_says_it_is_an_answer(client, seen):
    seen.outcomes.append(answered())

    assert client.post(COMPARE, json=BODY).json()["kind"] == "answer"


@pytest.mark.parametrize("reply", ["0.82 on validation", ""])
def test_the_reply_and_a_skip_both_reach_ask(client, seen, reply):
    """The empty text is a skip. It must arrive as "", not as None."""
    seen.outcomes.append(answered())

    client.post(COMPARE, json=BODY | {"thread_id": "chat-1", "reply": reply})

    assert seen[0]["reply"] == reply
    assert seen[0]["thread_id"] == "chat-1"


def test_a_normal_message_sends_no_reply(client, seen):
    seen.outcomes.append(answered())

    client.post(COMPARE, json=BODY)

    assert seen[0]["reply"] is None
