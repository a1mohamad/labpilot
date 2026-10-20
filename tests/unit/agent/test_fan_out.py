import pytest

from labpilot.agent.fan_out import fan_out
from labpilot.agent.plan import Plan, Query

SIDES = {"A": "stored A", "B": "stored B"}


def state(*, queries=(), a="A-1", b="B-1", question="why?"):
    return {
        "question": question,
        "a": a,
        "b": b,
        "sides": SIDES,
        "plan": Plan(steps=(), queries=tuple(queries)),
    }


def test_the_question_is_searched_first_on_each_side_then_the_plan_queries_follow():
    queries = [Query("B", "clipping"), Query("A", "learning rate"), Query("B", "seed")]

    sends = fan_out(state(queries=queries))

    assert [send.arg["query"] for send in sends] == [
        Query("A", "why?"),
        Query("B", "why?"),
        *queries,
    ]


def test_every_send_goes_to_search_one_and_carries_only_the_side_of_its_query():
    sends = fan_out(state(queries=[Query("B", "clipping")]))

    assert {send.node for send in sends} == {"search_one"}
    for send in sends:
        side = send.arg["query"].side
        assert send.arg["sides"] == {side: SIDES[side]}


def test_a_plan_query_equal_to_the_question_is_not_searched_twice():
    sends = fan_out(state(queries=[Query("B", "why?"), Query("B", "seed")]))

    assert [send.arg["query"] for send in sends] == [
        Query("A", "why?"),
        Query("B", "why?"),
        Query("B", "seed"),
    ]


def test_the_question_is_searched_on_a_side_the_plan_never_names():
    sends = fan_out(state(queries=[Query("A", "learning rate")]))

    assert Query("B", "why?") in [send.arg["query"] for send in sends]


def test_a_plan_with_no_query_searches_the_question_on_each_side_with_a_file():
    sends = fan_out(state(queries=[], question="why do they differ?"))

    assert [send.arg["query"] for send in sends] == [
        Query("A", "why do they differ?"),
        Query("B", "why do they differ?"),
    ]


def test_a_plan_with_no_query_skips_a_side_that_has_no_file():
    sends = fan_out(state(queries=[], a=""))

    assert [send.arg["query"].side for send in sends] == ["B"]


def test_nothing_to_search_is_an_error_and_not_a_quiet_stop():
    with pytest.raises(ValueError, match="nothing to search"):
        fan_out(state(queries=[], a="", b=""))
