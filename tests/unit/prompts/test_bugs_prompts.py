import pytest

from labpilot.prompts import HUNTS, build_hunt_prompt, build_skeptic_prompt
from labpilot.prompts.bugs import CONCEPT, METHOD, SKEPTIC, TRACE
from labpilot.prompts.checklists import (
    CHECKLIST_AUDIT,
    CHECKLISTS,
    OUTLINE_CHARS,
    PITFALLS,
    STANDARDS,
    build_checklist_audit_prompt,
    build_checklist_prompt,
)


def test_the_three_hunts_are_the_trace_the_method_and_the_concept():
    assert [hunt.instructions for hunt in HUNTS] == [TRACE, METHOD, CONCEPT]


def test_only_the_trace_is_small_and_only_the_method_reads_no_summary():
    small = [hunt.instructions for hunt in HUNTS if hunt.small]
    no_summary = [hunt.instructions for hunt in HUNTS if not hunt.with_summary]

    assert small == [TRACE]
    assert no_summary == [METHOD]


def test_the_big_hunts_follow_the_files_and_the_trace_does_not():
    by_file = {hunt.instructions.name: hunt.by_file for hunt in HUNTS}

    assert by_file == {TRACE.name: False, METHOD.name: True, CONCEPT.name: True}


def test_a_hunt_numbers_the_parts_and_puts_the_summary_before_them():
    prompt = build_hunt_prompt(TRACE, ["code a", "code b"], "an optimiser")

    assert prompt.startswith(TRACE.header)
    assert prompt.index("an optimiser") < prompt.index("[part 0]\ncode a")
    assert "[part 1]\ncode b" in prompt
    assert prompt.endswith(TRACE.closing)


def test_a_hunt_with_no_part_is_a_bug_of_the_caller():
    with pytest.raises(ValueError):
        build_hunt_prompt(TRACE, [])


def test_the_skeptic_numbers_the_suspects_from_zero():
    prompt = build_skeptic_prompt(["code"], ["[code] a", "[logic] b"])

    assert prompt.startswith(SKEPTIC.header)
    assert "0. [code] a\n1. [logic] b" in prompt


def test_the_two_checklists_are_the_standards_and_the_pitfalls():
    assert CHECKLISTS == (STANDARDS, PITFALLS)


def test_a_checklist_question_reads_the_summary_and_each_header_once():
    prompt = build_checklist_prompt(
        STANDARDS, "an optimiser", ["[adam.py · def step]", "[adam.py · def step]", ""]
    )

    assert prompt.startswith(STANDARDS.header)
    assert "an optimiser" in prompt
    assert prompt.count("[adam.py · def step]") == 1


def test_the_headers_are_cut_to_the_outline_size():
    prompt = build_checklist_prompt(PITFALLS, "s", ["x" * 100] * 200)

    assert len(prompt) < len(PITFALLS.header) + OUTLINE_CHARS + 200


def test_a_checklist_with_nothing_to_read_is_a_bug_of_the_caller():
    with pytest.raises(ValueError):
        build_checklist_prompt(STANDARDS, "", [])


def test_the_audit_numbers_the_rules_and_the_parts_from_zero():
    prompt = build_checklist_audit_prompt(
        ["Is it A?", "Is it B?"], ["code a", "code b"]
    )

    assert prompt.startswith(CHECKLIST_AUDIT.header)
    assert "0. Is it A?\n1. Is it B?" in prompt
    assert "[part 0]\ncode a" in prompt and "[part 1]\ncode b" in prompt


@pytest.mark.parametrize("rules, parts", [([], ["code"]), (["Is it A?"], [])])
def test_an_audit_with_no_rule_or_no_part_is_a_bug_of_the_caller(rules, parts):
    with pytest.raises(ValueError):
        build_checklist_audit_prompt(rules, parts)


def test_the_trace_asks_for_the_order_and_the_signs_and_the_skeptic_for_repeats():
    assert "ORDER and the SIGNS" in TRACE.header
    assert '"repeat"' in SKEPTIC.header and "same_as" in SKEPTIC.header
