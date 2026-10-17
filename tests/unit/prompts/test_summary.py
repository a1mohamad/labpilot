import pytest

from labpilot.prompts import SUMMARY, build_summary_prompt
from labpilot.tokens import estimate_tokens

BIG = 15_000


def test_every_part_is_sent_when_they_all_fit():
    prompt = build_summary_prompt(["alpha body", "beta body"])

    assert "All 2 parts are sent" in prompt
    assert "alpha body" in prompt
    assert "beta body" in prompt


def test_only_the_first_parts_that_fit_are_sent_and_the_prompt_says_so():
    parts = ["A" * BIG, "B" * BIG, "C" * BIG]
    assert estimate_tokens(parts[0]) == 5_000

    prompt = build_summary_prompt(parts)

    assert "Only the first 2 of 3 parts are sent" in prompt
    assert "A" * BIG in prompt
    assert "B" * BIG in prompt
    assert "C" * BIG not in prompt


def test_the_parts_keep_their_order():
    prompt = build_summary_prompt(["alpha body", "beta body", "gamma body"])

    positions = [prompt.index(p) for p in ("alpha body", "beta body", "gamma body")]
    assert positions == sorted(positions)


def test_the_instruction_comes_first_and_the_closing_comes_last():
    prompt = build_summary_prompt(["alpha body"])

    assert prompt.startswith(SUMMARY.header)
    assert prompt.endswith(SUMMARY.closing)


def test_a_summary_of_nothing_is_refused():
    with pytest.raises(ValueError):
        build_summary_prompt([])
