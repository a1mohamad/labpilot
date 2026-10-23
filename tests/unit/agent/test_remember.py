from langgraph.types import Overwrite

from labpilot.agent import Claim, Finding
from labpilot.agent.remember import make_remember_node

CLAIM = Claim("a fact", "[paper.md]", "a fact")
FINDING = Finding(CLAIM, "match", "", "[solver.py]", "a fact", "the same")
STATE = {"question": "why?", "result": "the result"}


def test_the_question_is_added_to_the_history():
    assert make_remember_node(None)(STATE) == {"history": ["why?"]}


def test_the_last_answer_is_written_when_a_function_gives_its_text():
    remembered = make_remember_node(lambda result: f"text of {result}")(STATE)

    assert remembered["last_answer"] == "text of the result"


def test_the_claims_and_the_findings_of_this_message_are_cleared():
    state = {**STATE, "claims": (CLAIM,), "findings": [FINDING]}

    remembered = make_remember_node(None)(state)

    assert remembered["claims"] == ()
    assert remembered["findings"] == Overwrite([])


def test_a_key_that_holds_nothing_is_not_written_at_all():
    remembered = make_remember_node(None)({**STATE, "claims": (), "findings": []})

    assert "claims" not in remembered and "findings" not in remembered
