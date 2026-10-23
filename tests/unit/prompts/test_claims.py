import re

import pytest

from labpilot.prompts import (
    CLAIMS,
    CLAIMS_BUDGET,
    build_claims_prompt,
    claims_fit,
)
from labpilot.tokens import estimate_tokens

QUESTION = "Why do the results differ?"
COLLAPSE_BYTES = 2200
BANNED = (
    "python",
    "pytorch",
    "gradient",
    "dataset",
    "function",
    "class",
    "variable",
    "repository",
    "epoch",
)


def test_the_instruction_comes_first_and_the_closing_comes_last():
    prompt = build_claims_prompt(["alpha body"], QUESTION)

    assert prompt.startswith(CLAIMS.header)
    assert prompt.endswith(CLAIMS.closing)


def test_the_question_is_in_the_prompt():
    assert QUESTION in build_claims_prompt(["alpha body"], QUESTION)


def test_every_part_is_numbered_from_zero_in_its_order():
    prompt = build_claims_prompt(["alpha body", "beta body", "gamma body"], QUESTION)

    assert "[part 0]\nalpha body" in prompt
    assert "[part 1]\nbeta body" in prompt
    assert "[part 2]\ngamma body" in prompt
    positions = [prompt.index(f"[part {n}]") for n in range(3)]
    assert positions == sorted(positions)


def test_claims_of_nothing_are_refused():
    with pytest.raises(ValueError):
        build_claims_prompt([], QUESTION)


def test_a_reference_over_the_budget_is_refused_and_not_cut():
    big = "x" * 45_000
    assert 2 * estimate_tokens(big) > CLAIMS_BUDGET

    assert claims_fit([big, big]) is False
    with pytest.raises(ValueError):
        build_claims_prompt([big, big], QUESTION)


def test_a_reference_exactly_as_big_as_the_budget_still_fits():
    assert claims_fit(["x" * (3 * CLAIMS_BUDGET)]) is True
    assert claims_fit(["x" * (3 * CLAIMS_BUDGET + 1)]) is False


def test_a_reference_of_a_normal_paper_fits():
    paper = "x" * 45_000
    assert estimate_tokens(paper) == 15_000

    assert claims_fit([paper]) is True


def test_the_instruction_stays_small():
    size = len(f"{CLAIMS.header}\n{CLAIMS.closing}".encode())

    assert size < COLLAPSE_BYTES


def test_the_instruction_names_no_language_and_no_field():
    text = f"{CLAIMS.header}\n{CLAIMS.closing}".lower()

    found = [word for word in BANNED if re.search(rf"\b{word}\b", text)]
    assert not found


def test_the_question_orders_the_claims_and_never_removes_one():
    header = " ".join(CLAIMS.header.split())

    assert "write the claims about that topic first" in header
    assert "Do not leave out other claims" in header
