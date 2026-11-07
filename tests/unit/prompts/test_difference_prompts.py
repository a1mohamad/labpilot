import pytest

from labpilot.prompts.audit import AUDIT, build_audit_prompt
from labpilot.prompts.review import (
    JUDGE,
    MERGE,
    build_judge_prompt,
    build_merge_prompt,
)
from labpilot.prompts.scan import SCAN, build_scan_prompt

FACTS = ["fact zero", "fact one", "fact two"]
PARTS = ["code part a", "code part b"]


def test_the_audit_lists_only_the_asked_facts_by_their_own_numbers():
    prompt = build_audit_prompt(FACTS, [1, 2], PARTS)

    assert prompt.startswith(AUDIT.header)
    assert "1. fact one" in prompt
    assert "2. fact two" in prompt
    assert "fact zero" not in prompt
    assert "[part 0]\ncode part a" in prompt
    assert prompt.endswith(AUDIT.closing)


def test_the_audit_says_a_rule_can_apply_in_more_than_one_place():
    assert "more than one place" in AUDIT.header


@pytest.mark.parametrize("numbers, parts", [([], PARTS), ([0], [])])
def test_the_audit_refuses_an_empty_call(numbers, parts):
    with pytest.raises(ValueError):
        build_audit_prompt(FACTS, numbers, parts)


def test_the_scan_puts_what_a_states_before_the_code():
    prompt = build_scan_prompt("A says the key is 128 bits", PARTS)

    assert prompt.startswith(SCAN.header)
    assert prompt.index("A says the key") < prompt.index("[part 0]")
    assert "[part 1]\ncode part b" in prompt


@pytest.mark.parametrize("reference, parts", [("  ", PARTS), ("A", [])])
def test_the_scan_refuses_an_empty_call(reference, parts):
    with pytest.raises(ValueError):
        build_scan_prompt(reference, parts)


def test_the_judge_numbers_findings_from_the_given_start_and_shows_a():
    prompt = build_judge_prompt(["first", "second"], 30, PARTS, reference="A text")

    assert prompt.startswith(JUDGE.header)
    assert "30. first" in prompt
    assert "31. second" in prompt
    assert "A text" in prompt
    assert prompt.index("A text") < prompt.index("[part 0]") < prompt.index("30. first")


def test_the_judge_leaves_out_the_reference_when_there_is_none():
    assert "WHAT A STATES" not in build_judge_prompt(["x"], 0, PARTS)


def test_the_judge_knows_a_setting_that_is_off_is_not_a_real_finding():
    assert "setting that is off" in JUDGE.header


def test_the_merge_lists_findings_by_their_own_numbers():
    prompt = build_merge_prompt({3: "B does not check X", 7: "X is accepted"})

    assert prompt.startswith(MERGE.header)
    assert "3. B does not check X" in prompt
    assert "7. X is accepted" in prompt


def test_the_merge_needs_two_findings():
    with pytest.raises(ValueError):
        build_merge_prompt({0: "alone"})
