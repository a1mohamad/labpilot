import pytest

from labpilot.agent.respond import make_respond_node


def state(a, b):
    return {
        "question": "explain it",
        "a": a,
        "b": b,
        "chunks": (),
        "totals": None,
        "summary_a": "",
        "summary_b": "",
    }


def asked_with(a, b):
    seen = {}

    def make_prompt(chunks, **kwargs):
        seen.update(kwargs)
        return "the prompt", chunks

    respond = make_respond_node(make_prompt, generate=lambda prompt: "answer")
    respond(state(a, b))
    return seen


def test_a_alone_is_answered_as_a_reference():
    # D106: the file in slot A alone is the reference, explained and not checked.
    seen = asked_with("A-1", "")

    assert seen["reference"] is True
    assert seen["files"] == 1


@pytest.mark.parametrize(("a", "b"), [("", "B-1"), ("A-1", "B-1"), ("", "")])
def test_any_other_case_is_not_a_reference(a, b):
    assert asked_with(a, b)["reference"] is False
