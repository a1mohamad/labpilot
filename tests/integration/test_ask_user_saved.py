"""The pause that asks the person one question, with the REAL graph and the REAL
saver (D109).

The unit tests use an in-memory saver and a fake graph. Here the pause is saved
in Postgres, the answer comes in a second call, and the run goes on from the
saved state, as it will over two HTTP requests.
"""

from __future__ import annotations

import pytest

from labpilot.api import asking
from labpilot.api.checkpoints import open_saver
from labpilot.api.contracts import Comparison, Question
from labpilot.api.errors import NothingToAnswer
from tests.integration.test_ask import FakeClient, stored

pytestmark = pytest.mark.database

QUESTION = "My F1 came out lower than the paper. Why?"
ASK = "Which F1 did you get, and on validation or test?"
PLAN = {"steps": [], "queries": [], "ask": ASK}


def start(db, chat: str, client: FakeClient, **kwargs):
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)
    return asking.ask(
        db, a, b, question=QUESTION, client=client, thread_id=chat, **kwargs
    ), (a, b)


def test_the_run_pauses_saves_and_goes_on_from_the_saved_state(db, chat_tables):
    client = FakeClient(plan=PLAN)

    paused, (a, b) = start(db, "pause-1", client)

    assert paused == Question(text=ASK)
    assert client.prompts == []
    config = {"configurable": {"thread_id": "pause-1"}}
    assert open_saver(db).get_tuple(config) is not None

    answer = asking.ask(
        db,
        a,
        b,
        question=QUESTION,
        client=client,
        thread_id="pause-1",
        reply="0.82 on validation",
    )

    assert isinstance(answer, Comparison)
    assert "Answer: 0.82 on validation" in client.prompts[-1]
    assert "you said" in client.prompts[-1]
    assert len(client.planner_prompts) == 1
    assert len(client.summary_prompts) == 2


def test_a_skip_gives_an_answer_with_no_note(db, chat_tables):
    client = FakeClient(plan=PLAN)
    paused, (a, b) = start(db, "pause-skip", client)

    answer = asking.ask(
        db, a, b, question=QUESTION, client=client, thread_id="pause-skip", reply=""
    )

    assert isinstance(answer, Comparison)
    assert "Asked:" not in client.prompts[-1]


def test_a_second_reply_to_the_same_pause_is_refused(db, chat_tables):
    client = FakeClient(plan=PLAN)
    paused, (a, b) = start(db, "pause-twice", client)
    asking.ask(
        db, a, b, question=QUESTION, client=client, thread_id="pause-twice", reply="x"
    )

    with pytest.raises(NothingToAnswer):
        asking.ask(
            db,
            a,
            b,
            question=QUESTION,
            client=client,
            thread_id="pause-twice",
            reply="y",
        )


def test_a_chat_with_no_id_never_pauses_even_when_the_plan_asks(db):
    client = FakeClient(plan=PLAN)
    a = stored(db, "A", parts=3, words=20)
    b = stored(db, "B", parts=3, words=20)

    answer = asking.ask(db, a, b, question=QUESTION, client=client)

    assert isinstance(answer, Comparison)
    assert "Asked:" not in client.prompts[-1]


def test_no_question_in_the_plan_means_no_pause_with_a_saved_chat(db, chat_tables):
    client = FakeClient()

    answer, _ = start(db, "pause-none", client)

    assert isinstance(answer, Comparison)
