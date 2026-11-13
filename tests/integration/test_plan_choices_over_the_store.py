"""The planner's choices (D107) through the real `ask()`, the real graph, the real
saver and a real database. The unit tests use fakes for every function the graph
is handed; these cross the joins between the plan, the graph, `respond`, the
saved results and the chat that is saved between two messages."""

import pytest

from labpilot.agent import Bug
from labpilot.api import asking
from tests.integration.test_ask import PLAN, FakeClient
from tests.integration.test_saved_results import stored

pytestmark = pytest.mark.database

BUG = Bug("logic", "the step is never updated", "[B.py - part 0]", "word word")
CHAT = {**PLAN, "files": False}
ABOUT_B = {**PLAN, "about": "B"}
AUDIT_ANSWER = {
    "answers": [
        {
            "n": 0,
            "verdict": "missing",
            "part": 0,
            "quote": "word word",
            "why": "B never does it",
        }
    ]
}


class AuditClient(FakeClient):
    """The audit's tool is answered: fact 0 is missing in B. Calls are counted."""

    audits = 0

    def generate(self, prompt, *, max_tokens=0, tool=None, problem_with=None):
        if tool is not None and tool.name == "give_verdicts":
            type(self).audits += 1
            result = super().generate(prompt, max_tokens=0, tool=None)
            return type(result)(
                text="a verdict",
                model="fake",
                tier=1,
                finish_reason="STOP",
                arguments=AUDIT_ANSWER,
            )
        return super().generate(
            prompt, max_tokens=max_tokens, tool=tool, problem_with=problem_with
        )


def test_a_chat_question_in_a_saved_chat_drops_the_files_of_the_message_before(
    db, chat_tables, monkeypatch
):
    a = stored(db, "A")
    b = stored(db, "B")
    monkeypatch.setattr(
        asking, "make_bug_finder", lambda conn, **clients: lambda artifact, s: (BUG,)
    )
    first_plan = {**PLAN, "steps": ["find_bugs"]}

    first = asking.ask(
        db, a, b, question="why?", client=FakeClient(first_plan), thread_id="d107"
    )
    second = asking.ask(
        db, a, b, question="What is HMAC?", client=FakeClient(CHAT), thread_id="d107"
    )

    assert first.chunks and "word word" in first.prompt
    # The saved chat held the chunks and totals of the first message; the chat
    # answer must overwrite them, or the reply would show files it never read.
    assert second.chunks == () and second.totals is None
    assert second.selected == ()
    assert "word word" not in second.prompt
    assert "the step is never updated" not in second.prompt
    # The saved bugs exist, and a chat question still does not read them.
    assert second.reused == ()


def test_a_question_about_b_is_answered_from_b_alone(db):
    a = stored(db, "A")
    b = stored(db, "B")

    answer = asking.ask(db, a, b, question="what is in B?", client=FakeClient(ABOUT_B))

    assert answer.chunks and {c.side for c in answer.chunks} == {"B"}
    assert "[B.py" in answer.prompt
    assert "[A.py" not in answer.prompt


def test_a_fresh_question_is_checked_once_and_then_read_from_the_database(db):
    a = stored(db, "A")
    b = stored(db, "B")
    AuditClient.audits = 0
    fresh_plan = {**PLAN, "fresh": True}
    question = "Does the code ever do it?"

    first = asking.ask(db, a, b, question=question, client=AuditClient(fresh_plan))
    audits_after_first = AuditClient.audits
    second = asking.ask(db, a, b, question=question, client=AuditClient(fresh_plan))

    assert audits_after_first > 0
    assert f'Asked "{question}": B never does it' in first.prompt
    assert first.reused == ()
    assert "fresh" in second.reused
    assert AuditClient.audits == audits_after_first


def test_a_question_that_is_not_fresh_makes_no_new_check(db):
    a = stored(db, "A")
    b = stored(db, "B")
    AuditClient.audits = 0

    answer = asking.ask(db, a, b, question="what is it?", client=AuditClient(PLAN))

    assert AuditClient.audits == 0
    assert "Asked " not in answer.prompt
