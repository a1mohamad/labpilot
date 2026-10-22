import threading

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from labpilot.agent import Plan, build_graph
from labpilot.agent.rewrite import make_rewrite_node
from labpilot.ingest import Chunk

STANDALONE = "what is the learning rate in A and B?"
FOLLOW_UP = "and the learning rate?"
FIRST = "why do the results differ?"
ANSWER = "Option 1: clip. Option 2: lower the lr."


def chunk(side):
    return Chunk(
        text="lr = 3e-4",
        source="train.py",
        start_line=1,
        end_line=2,
        side=side,
        artifact_id=f"{side}-1",
        chunk_index=0,
    )


CHUNK_A = chunk("A")
CHUNK_B = chunk("B")


class Boom(Exception):
    pass


def state(question=FOLLOW_UP, history=(FIRST,), last_answer=ANSWER):
    return {
        "question": question,
        "history": list(history),
        "last_answer": last_answer,
    }


# ---- the node alone --------------------------------------------------------


def test_the_first_message_of_a_chat_is_never_rewritten():
    calls = []
    node = make_rewrite_node(lambda q, h, a: calls.append(q) or "x")

    assert node(state(history=())) == {}
    assert node({"question": FIRST}) == {}
    assert calls == []


def test_a_follow_up_gets_the_questions_and_the_last_answer_and_is_replaced():
    seen = []

    def rewrite(question, history, last_answer):
        seen.append((question, history, last_answer))
        return STANDALONE

    result = make_rewrite_node(rewrite)(state())

    assert result == {"question": STANDALONE}
    assert seen == [(FOLLOW_UP, [FIRST], ANSWER)]


def test_a_chat_saved_before_last_answer_existed_gets_an_empty_one():
    seen = []

    def rewrite(question, history, last_answer):
        seen.append(last_answer)
        return STANDALONE

    make_rewrite_node(rewrite)({"question": FOLLOW_UP, "history": [FIRST]})

    assert seen == [""]


def test_the_answer_is_made_one_line():
    node = make_rewrite_node(lambda q, h, a: "  what is\n  the   lr?  ")

    assert node(state()) == {"question": "what is the lr?"}


@pytest.mark.parametrize("answer", ["", "   \n "])
def test_a_blank_answer_keeps_the_question(answer):
    assert make_rewrite_node(lambda q, h, a: answer)(state()) == {}


def test_an_answer_that_is_the_question_changes_nothing():
    node = make_rewrite_node(lambda question, h, a: f"  {question}  ")

    assert node(state()) == {}


def test_an_error_from_the_function_reaches_the_caller_unchanged():
    def rewrite(question, history, last_answer):
        raise Boom(question)

    with pytest.raises(Boom):
        make_rewrite_node(rewrite)(state())


# ---- inside the real graph ------------------------------------------------


def make_graph(
    calls,
    *,
    rewrite,
    fits_value=True,
    saver=None,
    summarize=None,
    on_plan=None,
    answer_text=None,
    generate=None,
):
    def plan(question, a, b):
        calls.append(("plan", question))
        if on_plan is not None:
            on_plan()
        return Plan(steps=(), queries=())

    def stuff(sides, question):
        calls.append(("stuff", question))
        return (CHUNK_A, CHUNK_B), None

    def search_one(sides, query):
        calls.append(("search_one", query.side, query.text))
        return (CHUNK_A if query.side == "A" else CHUNK_B,)

    def rank_side(question, pile):
        calls.append(("rank_side", question))
        return pile

    def make_prompt(chunks, question, totals, summaries, files, last_answer):
        calls.append(("make_prompt", question))
        return "the prompt", chunks

    return build_graph(
        measure=lambda a, b: {"A": "stored A", "B": "stored B"},
        fits=lambda sides, question: fits_value,
        stuff=stuff,
        search_one=search_one,
        totals_of=lambda sides: {"A": 5, "B": 9},
        rank_side=rank_side,
        plan=plan,
        make_prompt=make_prompt,
        generate=generate or (lambda prompt: "the result"),
        rewrite=rewrite,
        summarize=summarize,
        answer_text=answer_text,
        checkpointer=saver,
    )


def say(graph, question, chat="chat-7"):
    config = {"configurable": {"thread_id": chat}}
    return graph.invoke({"question": question, "a": "A-1", "b": "B-1"}, config)


def test_a_follow_up_is_rewritten_before_anything_reads_it():
    calls = []

    def rewrite(question, history, last_answer):
        calls.append(("rewrite", question, history))
        return STANDALONE

    graph = make_graph(calls, rewrite=rewrite, saver=InMemorySaver())
    say(graph, FIRST)
    calls.clear()

    final = say(graph, FOLLOW_UP)

    assert calls == [
        ("rewrite", FOLLOW_UP, [FIRST]),
        ("plan", STANDALONE),
        ("stuff", STANDALONE),
        ("make_prompt", STANDALONE),
    ]
    assert final["question"] == STANDALONE


def test_the_search_path_searches_and_ranks_the_standalone_question():
    calls = []
    graph = make_graph(
        calls,
        rewrite=lambda question, history, last_answer: STANDALONE,
        fits_value=False,
        saver=InMemorySaver(),
    )
    say(graph, FIRST)
    calls.clear()

    say(graph, FOLLOW_UP)

    searched = sorted(call[1:] for call in calls if call[0] == "search_one")
    assert searched == [("A", STANDALONE), ("B", STANDALONE)]
    assert [call for call in calls if call[0] == "rank_side"] == [
        ("rank_side", STANDALONE),
        ("rank_side", STANDALONE),
    ]


def test_the_chat_remembers_the_standalone_question_and_not_the_short_one():
    graph = make_graph([], rewrite=lambda q, h, a: STANDALONE, saver=InMemorySaver())

    say(graph, FIRST)
    final = say(graph, FOLLOW_UP)

    assert final["history"] == [FIRST, STANDALONE]


def test_the_chat_remembers_the_last_answer_and_the_next_rewrite_reads_it():
    seen = []

    def rewrite(question, history, last_answer):
        seen.append(last_answer)
        return STANDALONE

    graph = make_graph(
        [],
        rewrite=rewrite,
        answer_text=lambda result: f"excerpt of {result}",
        saver=InMemorySaver(),
    )

    first = say(graph, FIRST)
    second = say(graph, FOLLOW_UP)

    assert first["last_answer"] == "excerpt of the result"
    assert seen == ["excerpt of the result"]
    assert second["last_answer"] == "excerpt of the result"


def test_the_last_answer_is_replaced_by_each_message_and_not_added_to_a_list():
    answers = iter(["first answer", "second answer"])
    graph = make_graph(
        [],
        rewrite=lambda q, h, a: q,
        answer_text=str,
        generate=lambda prompt: next(answers),
        saver=InMemorySaver(),
    )

    say(graph, FIRST)
    final = say(graph, FOLLOW_UP)

    assert final["last_answer"] == "second answer"


def test_a_graph_given_no_answer_text_remembers_no_last_answer():
    graph = make_graph([], rewrite=lambda q, h, a: q, saver=InMemorySaver())

    final = say(graph, FIRST)

    assert "last_answer" not in final


def test_a_message_that_fails_does_not_replace_the_last_answer():
    outcomes = iter(["the first answer", Boom("model down")])

    def generate(prompt):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    saver = InMemorySaver()
    graph = make_graph(
        [],
        rewrite=lambda q, h, a: q,
        answer_text=str,
        generate=generate,
        saver=saver,
    )
    say(graph, FIRST)

    with pytest.raises(Boom):
        say(graph, FOLLOW_UP)

    saved = graph.get_state({"configurable": {"thread_id": "chat-7"}}).values
    assert saved["last_answer"] == "the first answer"


def test_the_first_message_and_a_chat_with_no_saver_are_never_rewritten():
    calls = []

    def rewrite(question, history, last_answer):
        calls.append(question)
        return STANDALONE

    graph = make_graph([], rewrite=rewrite, saver=InMemorySaver())
    say(graph, FIRST)
    assert calls == []

    # no saver: every message starts with an empty history
    bare = make_graph([], rewrite=rewrite)
    bare.invoke({"question": FOLLOW_UP, "a": "A-1", "b": "B-1"})
    assert calls == []


def test_a_graph_built_without_rewrite_leaves_the_follow_up_as_it_is():
    calls = []
    graph = make_graph(calls, rewrite=None, saver=InMemorySaver())
    say(graph, FIRST)
    calls.clear()

    say(graph, FOLLOW_UP)

    assert ("plan", FOLLOW_UP) in calls


def test_the_planner_and_both_summaries_still_run_together_after_the_rewrite():
    # Three threads must be inside their functions at the same moment. If the
    # rewrite made the summaries wait for the planner (or the other way), the
    # barrier would break and the message would fail.
    barrier = threading.Barrier(3, timeout=2)

    def summarize(artifact_id):
        barrier.wait()
        return artifact_id

    graph = make_graph(
        [],
        rewrite=lambda question, history, last_answer: STANDALONE,
        summarize=summarize,
        on_plan=barrier.wait,
        saver=InMemorySaver(),
    )
    say(graph, FIRST)

    final = say(graph, FOLLOW_UP)

    assert final["summary_a"] == "A-1"
    assert final["summary_b"] == "B-1"
