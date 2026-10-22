import inspect

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from labpilot.agent import Plan, build_graph
from labpilot.ingest import Chunk

SIDES = {"A": "stored A", "B": "stored B"}
TOTALS = {"A": 5, "B": 900}


class Boom(Exception):
    pass


def chunk(index, *, side="B"):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index + 1,
        side=side,
        artifact_id=f"{side}-1",
        chunk_index=index,
    )


STUFFED = (chunk(900), chunk(901))
FOUND_A = chunk(10, side="A")
FOUND_B = chunk(20, side="B")
NO_QUERY = Plan(steps=(), queries=())


def run(*, fits_value, fail_in=None):
    calls = []

    def fail(name):
        if fail_in == name:
            raise Boom(name)

    def plan(question, a, b):
        calls.append(("plan", question, a, b))
        return NO_QUERY

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

    def search_one(sides, query):
        calls.append(("search_one", query.side, query.text))
        fail("search_one")
        return (FOUND_A if query.side == "A" else FOUND_B,)

    def rank_side(question, pile):
        calls.append(("rank_side", question, pile))
        return pile

    def totals_of(sides):
        calls.append(("totals_of", sides))
        return TOTALS

    def make_prompt(chunks, question, totals, summaries, files, last_answer):
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
        search_one=search_one,
        totals_of=totals_of,
        rank_side=rank_side,
        plan=plan,
        make_prompt=make_prompt,
        generate=generate,
    )
    final = graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"})
    return final, calls


def names(calls):
    return [call[0] for call in calls]


def test_a_pair_that_fits_is_stuffed_and_never_searched():
    _, calls = run(fits_value=True)

    assert names(calls) == [
        "plan",
        "measure",
        "fits",
        "stuff",
        "make_prompt",
        "generate",
    ]


def test_a_pair_that_does_not_fit_is_searched_ranked_and_never_stuffed():
    _, calls = run(fits_value=False)

    # the two searches (the question on A and on B) run together, so only
    # their place in the line is fixed, not which one is written first
    assert names(calls) == [
        "plan",
        "measure",
        "fits",
        "search_one",
        "search_one",
        "rank_side",
        "rank_side",
        "totals_of",
        "make_prompt",
        "generate",
    ]


def test_every_function_gets_what_the_one_before_it_made():
    _, calls = run(fits_value=True)

    assert calls == [
        ("plan", "why?", "A-1", "B-1"),
        ("measure", "A-1", "B-1"),
        ("fits", SIDES, "why?"),
        ("stuff", SIDES, "why?"),
        ("make_prompt", STUFFED, "why?", None),
        ("generate", "the prompt"),
    ]


def test_the_stuff_path_says_nothing_was_left_out():
    final, _ = run(fits_value=True)

    assert final["totals"] is None


def test_the_search_path_hands_its_ranked_chunks_and_totals_to_the_prompt():
    final, calls = run(fits_value=False)

    assert ("make_prompt", (FOUND_A, FOUND_B), "why?", TOTALS) in calls
    assert final["totals"] == TOTALS


def test_the_question_is_searched_on_each_side_and_ranked_once_for_each():
    _, calls = run(fits_value=False)

    assert sorted(call[1:] for call in calls if call[0] == "search_one") == [
        ("A", "why?"),
        ("B", "why?"),
    ]
    assert [call[:3] for call in calls if call[0] == "rank_side"] == [
        ("rank_side", "why?", (FOUND_A,)),
        ("rank_side", "why?", (FOUND_B,)),
    ]


def test_the_final_state_holds_everything_ask_returns():
    final, _ = run(fits_value=True)

    assert final["result"] == "the result"
    assert final["chunks"] == STUFFED
    assert final["selected"] == STUFFED[:1]
    assert final["prompt"] == "the prompt"


@pytest.mark.parametrize("stage", ["measure", "search_one", "generate", "make_prompt"])
def test_an_error_from_a_function_reaches_the_caller_unchanged(stage):
    with pytest.raises(Boom, match=stage):
        run(fits_value=False, fail_in=stage)


@pytest.mark.parametrize("name", ["search_one", "totals_of", "rank_side", "plan"])
def test_the_functions_of_the_search_path_are_required_and_not_optional(name):
    # Optional ones made two ways to search, and the old one-shot `search` was
    # the way nothing used any more (D53). A default here would bring it back.
    parameter = inspect.signature(build_graph).parameters[name]

    assert parameter.default is inspect.Parameter.empty


def test_the_old_one_shot_search_is_not_a_parameter_any_more():
    assert "search" not in inspect.signature(build_graph).parameters


def chat_graph(saver=None, *, generate=None):
    return build_graph(
        measure=lambda a, b: SIDES,
        fits=lambda sides, question: True,
        stuff=lambda sides, question: (STUFFED, None),
        search_one=lambda sides, query: (FOUND_B,),
        totals_of=lambda sides: TOTALS,
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: NO_QUERY,
        make_prompt=lambda chunks, **_: ("the prompt", chunks[:1]),
        generate=generate or (lambda prompt: "the result"),
        checkpointer=saver,
    )


def say(graph, question, chat="chat-7"):
    config = {"configurable": {"thread_id": chat}}
    return graph.invoke({"question": question, "a": "A-1", "b": "B-1"}, config)


def test_a_second_message_in_the_same_chat_remembers_the_first():
    graph = chat_graph(InMemorySaver())

    say(graph, "first?")
    final = say(graph, "second?")

    assert final["history"] == ["first?", "second?"]


def test_two_chats_do_not_share_a_history():
    graph = chat_graph(InMemorySaver())

    say(graph, "first?", chat="chat-7")
    final = say(graph, "other?", chat="chat-8")

    assert final["history"] == ["other?"]


def test_a_graph_with_no_saver_remembers_only_the_current_message():
    final = chat_graph().invoke({"question": "first?", "a": "A-1", "b": "B-1"})

    assert final["history"] == ["first?"]


def test_a_message_that_fails_is_not_remembered():
    outcomes = iter([Boom("model down"), "the result"])

    def generate(prompt):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    graph = chat_graph(InMemorySaver(), generate=generate)

    with pytest.raises(Boom):
        say(graph, "fails?")
    final = say(graph, "works?")

    assert final["history"] == ["works?"]
