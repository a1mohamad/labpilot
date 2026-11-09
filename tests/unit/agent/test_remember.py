from langgraph.types import Overwrite

from labpilot.agent import Bug, Claim, Difference
from labpilot.agent.remember import make_remember_node

CLAIM = Claim("a fact", "[paper.md]", "a fact")
DIFFERENCE = Difference("differs", "B does it otherwise", "[solver.py]", "dt = 1")
BUG = Bug("code", "it divides by zero", "[solver.py]", "x / n")
STATE = {"question": "why?", "result": "the result"}


def test_the_question_is_added_to_the_history():
    assert make_remember_node(None)(STATE) == {"history": ["why?"]}


def test_the_last_answer_is_written_when_a_function_gives_its_text():
    remembered = make_remember_node(lambda result: f"text of {result}")(STATE)

    assert remembered["last_answer"] == "text of the result"


def test_the_claims_and_the_findings_of_this_message_are_cleared():
    state = {**STATE, "claims": (CLAIM,), "differences": [DIFFERENCE], "bugs": [BUG]}

    remembered = make_remember_node(None)(state)

    assert remembered["claims"] == ()
    assert remembered["differences"] == Overwrite([])
    assert remembered["bugs"] == Overwrite([])


def test_a_key_that_holds_nothing_is_not_written_at_all():
    state = {**STATE, "claims": (), "differences": [], "bugs": []}

    remembered = make_remember_node(None)(state)

    assert not {"claims", "differences", "bugs"} & set(remembered)
