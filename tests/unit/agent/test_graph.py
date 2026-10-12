import pytest

from labpilot.agent import build_graph

SIDES = object()
STUFFED = ("whole one", "whole two")
SEARCHED = ("found one", "found two")
TOTALS = {"A": 5, "B": 900}


class Boom(Exception):
    pass


def run(*, fits_value, fail_in=None):
    calls = []

    def fail(name):
        if fail_in == name:
            raise Boom(name)

    def measure(a, b):
        calls.append(("measure", a, b))
        fail("measure")
        return SIDES

    def fits(sides, question):
        calls.append(("fits", sides, question))
        return fits_value

    def stuff(sides, question):
        calls.append(("stuff", sides, question))
        return STUFFED, None

    def search(sides, question):
        calls.append(("search", sides, question))
        fail("search")
        return SEARCHED, TOTALS

    def make_prompt(chunks, question, totals):
        calls.append(("make_prompt", chunks, question, totals))
        return "the prompt", chunks[:1]

    def generate(prompt):
        calls.append(("generate", prompt))
        fail("generate")
        return "the result"

    graph = build_graph(
        measure=measure,
        fits=fits,
        stuff=stuff,
        search=search,
        make_prompt=make_prompt,
        generate=generate,
    )
    final = graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"})
    return final, calls


def names(calls):
    return [call[0] for call in calls]


def test_a_pair_that_fits_is_stuffed_and_never_searched():
    _, calls = run(fits_value=True)

    assert names(calls) == ["measure", "fits", "stuff", "make_prompt", "generate"]


def test_a_pair_that_does_not_fit_is_searched_and_never_stuffed():
    _, calls = run(fits_value=False)

    assert names(calls) == ["measure", "fits", "search", "make_prompt", "generate"]


def test_every_function_gets_what_the_one_before_it_made():
    _, calls = run(fits_value=True)

    assert calls == [
        ("measure", "A-1", "B-1"),
        ("fits", SIDES, "why?"),
        ("stuff", SIDES, "why?"),
        ("make_prompt", STUFFED, "why?", None),
        ("generate", "the prompt"),
    ]


def test_the_stuff_path_says_nothing_was_left_out():
    final, _ = run(fits_value=True)

    assert final["totals"] is None


def test_the_search_path_hands_its_totals_to_the_prompt():
    final, calls = run(fits_value=False)

    assert ("make_prompt", SEARCHED, "why?", TOTALS) in calls
    assert final["totals"] == TOTALS


def test_the_final_state_holds_everything_ask_returns():
    final, _ = run(fits_value=True)

    assert final["result"] == "the result"
    assert final["chunks"] == STUFFED
    assert final["selected"] == STUFFED[:1]
    assert final["prompt"] == "the prompt"


@pytest.mark.parametrize("stage", ["measure", "search", "generate"])
def test_an_error_from_a_function_reaches_the_caller_unchanged(stage):
    with pytest.raises(Boom, match=stage):
        run(fits_value=False, fail_in=stage)
