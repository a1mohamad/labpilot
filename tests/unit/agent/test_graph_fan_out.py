import threading

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from labpilot.agent import Plan, Query, build_graph
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


def keep_all(question, pile):
    return pile


def required():
    return {
        "measure": lambda a, b: SIDES,
        "fits": lambda sides, question: False,
        "stuff": lambda sides, question: (STUFFED, None),
        "make_prompt": lambda chunks, question, totals, summaries: (
            "the prompt",
            chunks[:1],
        ),
        "generate": lambda prompt: "the result",
    }


def fan_out_graph(*, search_one, queries=(), fits_value=False, checkpointer=None):
    def make_plan(question, a, b):
        return Plan(steps=(), queries=tuple(queries))

    return build_graph(
        **{**required(), "fits": lambda sides, question: fits_value},
        search_one=search_one,
        totals_of=lambda sides: TOTALS,
        rank_side=keep_all,
        plan=make_plan,
        checkpointer=checkpointer,
    )


def ask(graph, question="why?", chat=None):
    start = {"question": question, "a": "A-1", "b": "B-1"}
    if chat is None:
        return graph.invoke(start)
    return graph.invoke(start, {"configurable": {"thread_id": chat}})


def test_every_query_and_the_question_on_each_side_are_searched_once():
    calls = []

    def search_one(sides, query):
        calls.append((tuple(sides), query))
        return ()

    queries = [Query("B", "clipping"), Query("A", "learning rate")]

    ask(fan_out_graph(search_one=search_one, queries=queries))

    asked = [Query("A", "why?"), Query("B", "why?")]
    assert len(calls) == 4
    assert set(calls) == {((query.side,), query) for query in (*asked, *queries)}


def test_the_merged_chunks_and_the_totals_reach_the_prompt():
    answers = {
        "why?": (),
        "clipping": (chunk(1), chunk(2)),
        "seed": (chunk(2), chunk(3)),
    }
    seen = []

    def make_prompt(chunks, question, totals, summaries):
        seen.append((chunks, totals))
        return "the prompt", chunks[:1]

    graph = build_graph(
        **{**required(), "make_prompt": make_prompt},
        search_one=lambda sides, query: answers[query.text],
        totals_of=lambda sides: TOTALS,
        rank_side=keep_all,
        plan=lambda question, a, b: Plan(
            steps=(), queries=(Query("B", "clipping"), Query("B", "seed"))
        ),
    )

    final = ask(graph)

    merged = (chunk(1), chunk(2), chunk(3))
    assert seen == [(merged, TOTALS)]
    assert final["chunks"] == merged
    assert final["totals"] == TOTALS


def test_a_pair_that_fits_is_stuffed_and_no_search_runs():
    def search_one(sides, query):
        raise AssertionError("a pair that fits must not be searched")

    final = ask(
        fan_out_graph(search_one=search_one, queries=[Query("B", "x")], fits_value=True)
    )

    assert final["chunks"] == STUFFED


def test_the_searches_run_at_the_same_time():
    barrier = threading.Barrier(4, timeout=2)

    def search_one(sides, query):
        barrier.wait()
        return (chunk(len(query.text)),)

    queries = [Query("B", "one"), Query("B", "three")]

    final = ask(fan_out_graph(search_one=search_one, queries=queries))

    # the question on A and on B, plus the two plan queries: four at once
    assert [c.chunk_index for c in final["chunks"]] == [4, 3, 5]


def test_a_plan_with_no_query_searches_the_question_on_each_side():
    calls = []

    def search_one(sides, query):
        calls.append(query)
        return ()

    ask(fan_out_graph(search_one=search_one, queries=[]), question="why differ?")

    assert sorted(calls, key=lambda q: q.side) == [
        Query("A", "why differ?"),
        Query("B", "why differ?"),
    ]


def test_the_found_lists_are_emptied_when_the_merge_is_done():
    final = ask(
        fan_out_graph(
            search_one=lambda sides, query: (chunk(1),), queries=[Query("B", "x")]
        )
    )

    assert final["found"] == []


def test_a_second_message_does_not_inherit_the_chunks_of_the_first():
    def search_one(sides, query):
        return (chunk(len(query.text)),)

    def make_plan(question, a, b):
        return Plan(steps=(), queries=(Query("B", question),))

    # the saver stores what a Send carries, so the sides must be saveable
    graph = build_graph(
        **{**required(), "measure": lambda a, b: {"A": "stored A", "B": "stored B"}},
        search_one=search_one,
        totals_of=lambda sides: TOTALS,
        rank_side=keep_all,
        plan=make_plan,
        checkpointer=InMemorySaver(),
    )

    ask(graph, question="aaa", chat="chat-7")
    final = ask(graph, question="bbbbb", chat="chat-7")

    assert [c.chunk_index for c in final["chunks"]] == [5]


def test_an_error_in_one_search_reaches_the_caller_unchanged():
    def search_one(sides, query):
        if query.text == "clipping":
            raise Boom(query.text)
        return ()

    with pytest.raises(Boom, match="clipping"):
        ask(fan_out_graph(search_one=search_one, queries=[Query("B", "clipping")]))


def test_each_side_is_ranked_once_with_the_original_question_not_the_query():
    ranked = []

    def rank_side(question, pile):
        ranked.append((question, [(c.side, c.chunk_index) for c in pile]))
        return pile

    answers = {
        "why differ?": (),
        "clipping": (chunk(1), chunk(2)),
        "seed": (chunk(2), chunk(3)),
        "lr": (chunk(7, side="A"),),
    }
    graph = build_graph(
        **required(),
        search_one=lambda sides, query: answers[query.text],
        totals_of=lambda sides: TOTALS,
        rank_side=rank_side,
        plan=lambda question, a, b: Plan(
            steps=(),
            queries=(Query("B", "clipping"), Query("A", "lr"), Query("B", "seed")),
        ),
    )

    ask(graph, question="why differ?")

    assert ranked == [
        ("why differ?", [("A", 7)]),
        ("why differ?", [("B", 1), ("B", 2), ("B", 3)]),
    ]


def test_the_chunks_that_reach_the_prompt_are_the_ranked_ones():
    final = ask(
        build_graph(
            **required(),
            search_one=lambda sides, query: (chunk(1), chunk(2), chunk(3)),
            totals_of=lambda sides: TOTALS,
            rank_side=lambda question, pile: tuple(reversed(pile)),
            plan=lambda question, a, b: Plan(steps=(), queries=(Query("B", "x"),)),
        )
    )

    assert [c.chunk_index for c in final["chunks"]] == [3, 2, 1]


def test_an_error_in_the_ranking_reaches_the_caller_unchanged():
    def rank_side(question, pile):
        raise Boom("rank")

    graph = build_graph(
        **required(),
        search_one=lambda sides, query: (chunk(1),),
        totals_of=lambda sides: TOTALS,
        rank_side=rank_side,
        plan=lambda question, a, b: Plan(steps=(), queries=(Query("B", "x"),)),
    )

    with pytest.raises(Boom, match="rank"):
        ask(graph)


def test_the_old_one_shot_search_is_refused_by_the_builder():
    with pytest.raises(TypeError):
        build_graph(
            **required(),
            search=lambda sides, question: ((), None),
            search_one=lambda sides, query: (),
            totals_of=lambda sides: TOTALS,
            rank_side=keep_all,
            plan=lambda question, a, b: Plan(steps=(), queries=()),
        )


@pytest.mark.parametrize("missing", ["search_one", "plan", "totals_of", "rank_side"])
def test_a_graph_without_one_of_the_search_functions_cannot_be_built(missing):
    wiring = {
        "search_one": lambda sides, query: (),
        "plan": lambda question, a, b: Plan(steps=(), queries=()),
        "totals_of": lambda sides: TOTALS,
        "rank_side": keep_all,
    }
    del wiring[missing]

    with pytest.raises(TypeError, match=missing):
        build_graph(**required(), **wiring)
