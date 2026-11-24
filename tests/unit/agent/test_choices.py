import pytest

from labpilot.agent import Plan
from labpilot.agent.choices import FinderChoices, after_measure

ALL = FinderChoices(claims=True, differences=True, bugs=True, fresh=True)
NONE = FinderChoices(claims=False, differences=False, bugs=False, fresh=False)


def state(*steps, totals=None, a="A-1", b="B-1", **plan):
    return {
        "plan": Plan(steps=steps, queries=(), **plan),
        "question": "why?",
        "a": a,
        "b": b,
        "totals": totals,
    }


def names(sends):
    return [send.node for send in sends]


def test_a_question_that_needs_no_file_goes_straight_to_the_answer():
    assert after_measure(state(files=False) | {"fits": True}) == "respond"


def test_a_pair_that_fits_is_read_whole():
    assert after_measure(state(files=True) | {"fits": True}) == "stuff"


def test_a_pair_read_whole_runs_no_claims_and_no_differences():
    found = ALL.after_search(state("find_differences", "find_bugs"))

    assert names(found) == ["find_bugs"]


def test_a_searched_pair_lists_the_claims_first():
    searched = state("find_differences", "find_bugs", totals={"A": 1, "B": 2})

    assert ALL.after_search(searched) == "extract_claims"


def test_without_claims_the_finders_start_at_the_same_time():
    searched = state("find_differences", "find_bugs", totals={"A": 1, "B": 2})
    no_claims = FinderChoices(claims=False, differences=True, bugs=True, fresh=True)

    assert names(no_claims.after_search(searched)) == ["find_bugs", "find_differences"]


@pytest.mark.parametrize("totals", [None, {"A": 1, "B": 2}])
def test_a_graph_with_no_finders_always_answers(totals):
    searched = state("find_differences", "find_bugs", totals=totals, fresh=True)

    assert NONE.after_search(searched) == "respond"
    assert NONE.names() == []


def test_the_names_are_the_wired_finders_only():
    some = FinderChoices(claims=True, differences=False, bugs=True, fresh=False)

    assert some.names() == ["find_bugs"]
