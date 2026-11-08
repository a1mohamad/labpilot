import pytest

from labpilot.agent import (
    Bug,
    judged_bug,
    read_verdicts,
)

SOURCES = ["[train.py · def step · lines 1-9]", "[train.py · def eval · lines 10-19]"]


def bug(text="beta1 is used for the second moment", verdict="unchecked"):
    return Bug("logic", text, SOURCES[0], "beta1**step", "high", verdict)


def test_the_verdicts_are_read_by_number_and_a_bad_one_is_none():
    arguments = {
        "verdicts": [
            {"n": 1, "verdict": "real", "reason": " wrong beta "},
            {"n": 0, "verdict": "maybe"},
            {"n": 7, "verdict": "false"},
            {"n": True, "verdict": "false"},
        ]
    }

    assert read_verdicts(arguments, 3) == [None, ("real", "wrong beta"), None]
    assert read_verdicts(None, 2) == [None, None]


def test_one_real_vote_makes_a_suspect_real():
    got = judged_bug(bug(), [("false", "no"), ("real", "it is wrong")])

    assert (got.verdict, got.reason) == ("real", "it is wrong")


@pytest.mark.parametrize(
    "votes",
    [
        [("false", "a"), ("intended", "b")],
        [("intended", "a"), ("intended", "b")],
    ],
)
def test_a_suspect_is_thrown_out_only_when_every_vote_throws_it_out(votes):
    assert judged_bug(bug(), votes) is None


@pytest.mark.parametrize(
    "votes",
    [
        [("false", "a"), None],
        [("false", "a"), ("unclear", "b")],
    ],
)
def test_a_lost_or_split_vote_keeps_the_suspect_as_unclear(votes):
    # 2026-11-01: one vote dropped up to 6 of 17 real defects in a bad run.
    assert judged_bug(bug(), votes).verdict == "unclear"


def test_with_no_vote_at_all_the_suspect_is_shown_unchecked():
    assert judged_bug(bug(), [None, None]).verdict == "unchecked"


@pytest.mark.parametrize(
    "votes",
    [
        [("intended", "a"), ("intended", "b")],
        [("false", "a"), ("intended", "b")],
    ],
)
def test_a_concept_suspect_called_intended_is_kept_as_unclear(votes):
    concept = Bug("concept", "MD5 is accepted", SOURCES[0], "md5", "high")

    assert judged_bug(concept, votes).verdict == "unclear"


def test_a_concept_suspect_every_vote_calls_false_is_thrown_out():
    concept = Bug("concept", "MD5 is accepted", SOURCES[0], "md5", "high")

    assert judged_bug(concept, [("false", "a"), ("false", "b")]) is None


def test_a_repeat_vote_must_name_an_earlier_suspect():
    arguments = {
        "verdicts": [
            {"n": 0, "verdict": "real"},
            {"n": 1, "verdict": "repeat", "same_as": 0},
            {"n": 2, "verdict": "repeat", "same_as": 2},
            {"n": 3, "verdict": "repeat"},
        ]
    }

    got = read_verdicts(arguments, 4)

    assert got[1] == ("repeat", "") and got[2] is None and got[3] is None


@pytest.mark.parametrize("kind", ["logic", "concept"])
def test_a_suspect_every_vote_calls_a_repeat_is_thrown_out(kind):
    suspect = Bug(kind, "the same leak again", SOURCES[1], "best_on(val)")

    assert judged_bug(suspect, [("repeat", ""), ("repeat", "")]) is None
