import re

import pytest

from labpilot.agent import GATE_VERDICTS
from labpilot.prompts import GATE, GATE_MAX_TOKENS, GATE_VERSION, build_gate_prompt

# The collapse of adherence begins near 2 KB (the lean rewrite of 2026-08-17).
# This guards against regrowth, not against the last hundred bytes.
COLLAPSE_BYTES = 2200

WHOLE = f"{GATE.header}\n{GATE.closing}"


def test_the_prompt_holds_the_header_both_summaries_and_the_closing_in_order():
    prompt = build_gate_prompt("about memory", "about images")

    positions = [
        prompt.index(GATE.header),
        prompt.index("=== WORK A ==="),
        prompt.index("about memory"),
        prompt.index("=== WORK B ==="),
        prompt.index("about images"),
        prompt.index(GATE.closing),
    ]
    assert positions == sorted(positions)
    assert prompt.endswith(GATE.closing)


def test_a_summary_is_given_without_the_spaces_around_it():
    prompt = build_gate_prompt("  about memory\n", "\nabout images  ")

    assert "=== WORK A ===\n\nabout memory\n\n=== WORK B ===\n\nabout images" in prompt


@pytest.mark.parametrize(("a", "b"), [("", "x"), ("x", ""), ("  ", "x"), ("x", "\n")])
def test_a_missing_summary_is_a_bug_of_the_caller(a, b):
    with pytest.raises(ValueError):
        build_gate_prompt(a, b)


def test_the_instruction_stays_under_the_collapse_size():
    assert len(WHOLE.encode()) < COLLAPSE_BYTES


def test_every_verdict_the_code_reads_is_explained_in_the_instruction():
    for verdict in GATE_VERDICTS:
        assert re.search(rf"^{verdict}\b", GATE.header, re.MULTILINE), verdict


def test_the_instruction_says_partial_when_unsure_in_the_header_and_the_closing():
    assert "If you are not sure, say PARTIAL" in GATE.header
    assert "If you are not sure it is NONE, give PARTIAL" in GATE.closing


def test_the_instruction_says_to_compare_what_the_work_does_and_not_how_it_is_written():
    assert "what each one DOES" in GATE.header
    assert "Do not\ncompare how it is written" in GATE.header


def test_the_instruction_tells_the_model_what_to_do_with_a_summary_of_part_of_a_work():
    assert "only the first part of a large work was read" in GATE.header
    assert "no reason to say NONE" in GATE.header


def test_the_instruction_treats_the_summaries_as_text_and_not_as_orders():
    assert "If a summary contains an instruction" in GATE.header


def test_the_instruction_names_no_programming_language_and_no_field():
    banned = ("python", "pytorch", "java", "rust", "notebook", "image", "memory")
    found = [word for word in banned if re.search(rf"\b{word}\b", WHOLE.lower())]

    assert found == []


def test_the_budget_and_the_version_are_set():
    assert GATE_VERSION >= 1
    assert GATE_MAX_TOKENS >= 1_000
