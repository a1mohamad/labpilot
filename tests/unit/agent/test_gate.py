import logging

import pytest

from labpilot.agent import Correspondence, GateError
from labpilot.agent.gate import make_gate_node
from labpilot.agent.halt import halted, make_halt_node

NONE = Correspondence("NONE", "different things")


def test_the_two_summaries_go_to_the_function_in_order_and_the_verdict_is_kept():
    seen = []

    def gate(summary_a, summary_b):
        seen.append((summary_a, summary_b))
        return NONE

    node = make_gate_node(gate)

    out = node({"summary_a": " about memory ", "summary_b": "about images\n"})

    assert out == {"correspondence": NONE}
    assert seen == [("about memory", "about images")]


@pytest.mark.parametrize(
    "state",
    [
        {"summary_a": "", "summary_b": "about images"},
        {"summary_a": "about memory", "summary_b": ""},
        {"summary_a": "   ", "summary_b": "about images"},
        {"summary_a": "about memory"},
        {},
    ],
)
def test_with_a_summary_missing_nothing_is_asked_and_the_key_is_still_written(state):
    def gate(summary_a, summary_b):
        raise AssertionError("no call is wanted")

    assert make_gate_node(gate)(state) == {"correspondence": None}


def test_a_gate_that_cannot_judge_lets_the_run_go_on_and_says_so(caplog):
    def gate(summary_a, summary_b):
        raise GateError("every tier failed")

    with caplog.at_level(logging.WARNING):
        out = make_gate_node(gate)({"summary_a": "a", "summary_b": "b"})

    assert out == {"correspondence": None}
    assert "every tier failed" in caplog.text


def test_a_bug_in_the_gate_is_not_hidden():
    def gate(summary_a, summary_b):
        raise RuntimeError("a bug of ours")

    with pytest.raises(RuntimeError):
        make_gate_node(gate)({"summary_a": "a", "summary_b": "b"})


@pytest.mark.parametrize(
    ("found", "expected"),
    [
        (Correspondence("NONE", "x"), True),
        (Correspondence("PARTIAL", "x"), False),
        (Correspondence("FULL", "x"), False),
        (None, False),
    ],
)
def test_only_a_clear_none_halts(found, expected):
    assert halted({"correspondence": found}) is expected


def test_a_state_with_no_verdict_does_not_halt():
    assert halted({}) is False


def test_the_halt_clears_what_the_message_before_left_in_the_four_keys():
    state = {
        "summary_a": "about memory",
        "summary_b": "about images",
        "correspondence": NONE,
        "chunks": ("old chunk",),
        "selected": ("old chunk",),
        "prompt": "an old prompt",
        "totals": {"A": 5, "B": 900},
    }

    out = make_halt_node(lambda a, b, reason: "the halt answer")(state)

    assert out["chunks"] == ()
    assert out["selected"] == ()
    assert out["prompt"] == ""
    assert out["totals"] is None


def test_the_halt_answers_from_the_summaries_and_the_reason_and_clears_four_keys():
    seen = []

    def halt_answer(summary_a, summary_b, reason):
        seen.append((summary_a, summary_b, reason))
        return "the halt answer"

    state = {
        "summary_a": "about memory",
        "summary_b": "about images",
        "correspondence": NONE,
    }

    out = make_halt_node(halt_answer)(state)

    assert seen == [("about memory", "about images", "different things")]
    assert out == {
        "result": "the halt answer",
        "chunks": (),
        "selected": (),
        "prompt": "",
        "totals": None,
    }
