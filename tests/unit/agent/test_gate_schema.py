import pytest

from labpilot.agent import (
    GATE_VERDICTS,
    Correspondence,
    GateError,
    gate_schema,
    read_correspondence,
)
from labpilot.agent.gate_schema import MAX_REASON_CHARS


def test_the_schema_allows_exactly_the_three_verdicts():
    schema = gate_schema()

    assert schema["properties"]["verdict"]["enum"] == ["FULL", "PARTIAL", "NONE"]
    assert schema["required"] == ["verdict", "reason"]


def test_a_good_answer_becomes_a_correspondence():
    found = read_correspondence({"verdict": "NONE", "reason": "different things"})

    assert found == Correspondence("NONE", "different things")


@pytest.mark.parametrize("written", ["none", " None ", "Partial", "full"])
def test_the_case_and_the_spaces_of_a_verdict_do_not_matter(written):
    found = read_correspondence({"verdict": written, "reason": "because"})

    assert found.verdict in GATE_VERDICTS
    assert found.verdict == written.strip().upper()


@pytest.mark.parametrize("verdict", ["MAYBE", "", None, 3, True, ["NONE"]])
def test_a_verdict_that_is_not_one_of_the_three_is_refused(verdict):
    with pytest.raises(GateError, match="verdict"):
        read_correspondence({"verdict": verdict, "reason": "because"})


def test_a_missing_verdict_is_refused():
    with pytest.raises(GateError, match="verdict"):
        read_correspondence({"reason": "because"})


@pytest.mark.parametrize("reason", [None, "", "   ", 5, ["a reason"]])
def test_a_verdict_without_a_text_reason_is_refused(reason):
    with pytest.raises(GateError, match="reason"):
        read_correspondence({"verdict": "NONE", "reason": reason})


def test_the_reason_is_one_line():
    found = read_correspondence({"verdict": "NONE", "reason": "one\n\n  two\tthree "})

    assert found.reason == "one two three"


def test_a_long_reason_is_cut():
    found = read_correspondence({"verdict": "NONE", "reason": "word " * 500})

    assert 0 < len(found.reason) <= MAX_REASON_CHARS
