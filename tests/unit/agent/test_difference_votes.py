import pytest

from labpilot.agent import (
    DIFFERS,
    MISSING,
    SILENT,
    Difference,
    audit_findings,
    judged_findings,
    merged_findings,
)


def difference(text, kind=MISSING):
    return Difference(kind, text, "[f.py]", "x", fact=f"fact {text}")


FIRST = difference("first")
SECOND = difference("second")


def test_a_fact_one_vote_flags_is_a_difference():
    answers = [
        (0, {0: ("same", None)}),
        (1, {0: (MISSING, FIRST)}),
    ]

    assert audit_findings(answers, 1) == [FIRST]


def test_same_in_one_group_beats_missing_in_another_group_of_the_same_vote():
    # One vote read B in two groups: the rule is done in the second one.
    answers = [
        (0, {0: (MISSING, FIRST)}),
        (0, {0: ("same", None)}),
    ]

    assert audit_findings(answers, 1) == []


def test_a_fact_flagged_by_both_votes_is_given_once_and_in_fact_order():
    answers = [
        (0, {1: (DIFFERS, SECOND), 0: (MISSING, FIRST)}),
        (1, {0: (MISSING, difference("first again")), 1: (DIFFERS, SECOND)}),
    ]

    assert audit_findings(answers, 2) == [FIRST, SECOND]


def test_a_fact_no_call_answered_or_that_does_not_apply_is_no_difference():
    answers = [(0, {0: ("n/a", None)})]

    assert audit_findings(answers, 2) == []


def votes(*said):
    return {0: list(said)}


def test_one_real_vote_keeps_a_finding():
    (kept,) = judged_findings([FIRST], votes(("real", "differs"), ("minor", "none")))

    assert kept == FIRST


@pytest.mark.parametrize(
    "said",
    [
        [("false", "none"), ("false", "none")],
        [("minor", "none"), ("minor", "none")],
        [("minor", "none"), ("false", "none")],
    ],
    ids=["all false", "all minor", "minor and false"],
)
def test_a_finding_with_no_real_vote_is_hidden(said):
    assert judged_findings([FIRST], votes(*said)) == []


def test_real_and_false_keep_the_finding_as_unclear():
    (kept,) = judged_findings([FIRST], votes(("real", "differs"), ("false", "none")))

    assert kept.unclear is True


def test_a_finding_no_judge_answered_stays_as_it_is():
    assert judged_findings([FIRST], {}) == [FIRST]


def test_a_finding_every_judge_says_a_states_the_same_is_hidden():
    said = votes(("real", "same"), ("real", "same"))

    assert judged_findings([FIRST], said) == []


def test_a_scan_item_the_judges_say_a_states_otherwise_becomes_differs():
    silent = difference("extra step", kind=SILENT)

    (kept,) = judged_findings([silent], votes(("real", "differs"), ("real", "silent")))

    assert kept.kind == DIFFERS


def test_an_audit_finding_keeps_its_kind_whatever_the_relation():
    (kept,) = judged_findings([FIRST], votes(("real", "silent")))

    assert kept.kind == MISSING


def test_the_first_finding_of_a_group_stays_and_a_lone_one_is_kept():
    third = difference("third")

    kept = merged_findings([FIRST, SECOND, third], [[2, 0]])

    assert kept == [FIRST, SECOND]
