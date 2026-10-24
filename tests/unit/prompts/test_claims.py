import re

import pytest

from labpilot.prompts import (
    CLAIMS,
    CLAIMS_BUDGET,
    CLAIMS_GROUP_TOKENS,
    build_claims_prompt,
    claims_fit,
    claims_groups,
)
from labpilot.tokens import estimate_tokens

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
    prompt = build_claims_prompt(["alpha body"])

    assert prompt.startswith(CLAIMS.header)
    assert prompt.endswith(CLAIMS.closing)


def test_no_question_is_in_the_prompt():
    # A question narrowed the list from 12 claims to 5 (section 25.2), and a
    # group of parts cannot use one anyway.
    prompt = build_claims_prompt(["alpha body"])

    assert "QUESTION" not in prompt
    assert "question" not in CLAIMS.header.lower()


def test_every_part_is_numbered_from_zero_in_its_order():
    prompt = build_claims_prompt(["alpha body", "beta body", "gamma body"])

    assert "[part 0]\nalpha body" in prompt
    assert "[part 1]\nbeta body" in prompt
    assert "[part 2]\ngamma body" in prompt
    positions = [prompt.index(f"[part {n}]") for n in range(3)]
    assert positions == sorted(positions)


def test_claims_of_nothing_are_refused():
    with pytest.raises(ValueError):
        build_claims_prompt([])


def test_a_reference_over_the_budget_is_refused_and_not_cut():
    big = "x" * 45_000
    assert 2 * estimate_tokens(big) > CLAIMS_BUDGET

    assert claims_fit([big, big]) is False
    with pytest.raises(ValueError):
        build_claims_prompt([big, big])


def test_a_reference_exactly_as_big_as_the_budget_still_fits():
    assert claims_fit(["x" * (3 * CLAIMS_BUDGET)]) is True
    assert claims_fit(["x" * (3 * CLAIMS_BUDGET + 1)]) is False


def test_the_instruction_stays_small():
    size = len(f"{CLAIMS.header}\n{CLAIMS.closing}".encode())

    assert size < COLLAPSE_BYTES


def test_the_instruction_names_no_language_and_no_field():
    text = f"{CLAIMS.header}\n{CLAIMS.closing}".lower()

    found = [word for word in BANNED if re.search(rf"\b{word}\b", text)]
    assert not found


def test_the_instruction_asks_for_rules_and_steps_and_for_a_kind():
    header = " ".join(CLAIMS.header.split())

    assert "write one claim for each value" in header
    assert "the rules and the steps of the method" in header
    assert '"method"' in header and '"result"' in header


def part(tokens):
    return "x" * (3 * tokens)


def test_the_sample_paper_is_read_in_two_groups_of_nine_parts():
    # The sizes of the 18 parts of A_paper.md, in tokens: the measured arm of
    # section 25.2 was two groups of 9 parts, about 2,150 tokens each.
    sizes = [80, 220, 240, 165, 193, 323, 195, 342, 430]
    sizes += [262, 215, 212, 319, 104, 181, 352, 341, 131]

    groups = claims_groups([part(size) for size in sizes])

    assert groups == [list(range(0, 9)), list(range(9, 18))]


def test_every_part_is_in_exactly_one_group_and_the_order_is_kept():
    parts = [part(size) for size in (500, 900, 300, 1200, 50, 700, 650, 400)]

    groups = claims_groups(parts)

    assert [i for group in groups for i in group] == list(range(len(parts)))


def test_the_number_of_groups_is_the_total_over_the_target_rounded():
    parts = [part(500)] * 20  # 10,000 tokens

    groups = claims_groups(parts)

    assert len(groups) == round(10_000 / CLAIMS_GROUP_TOKENS)
    assert {len(group) for group in groups} == {4}


def test_a_small_reference_is_one_group():
    assert claims_groups([part(300), part(400)]) == [[0, 1]]


def test_a_part_bigger_than_the_target_is_never_cut():
    groups = claims_groups([part(5_000), part(100)])

    assert [i for group in groups for i in group] == [0, 1]
    assert all(group for group in groups)


def test_there_are_never_more_groups_than_parts():
    assert len(claims_groups([part(9_000)])) == 1
