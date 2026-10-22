import threading
import time

from labpilot.agent import Plan, build_graph
from labpilot.agent.respond import make_respond_node
from labpilot.ingest import Chunk

SIDES = {"A": "stored A", "B": "stored B"}


def chunk(index):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index + 1,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
    )


def test_respond_builds_the_prompt_from_the_state_and_generates_from_it():
    seen = []

    def make_prompt(chunks, question, totals, summaries, files, last_answer):
        seen.append((chunks, question, totals, summaries))
        return "the prompt", chunks[:1]

    node = make_respond_node(make_prompt, lambda prompt: f"answer to {prompt}")
    state = {
        "chunks": (chunk(1), chunk(2)),
        "question": "why?",
        "totals": {"A": 1, "B": 2},
        "summary_a": "sa",
        "summary_b": "sb",
    }

    out = node(state)

    assert seen == [
        ((chunk(1), chunk(2)), "why?", {"A": 1, "B": 2}, {"A": "sa", "B": "sb"})
    ]
    assert out == {
        "prompt": "the prompt",
        "selected": (chunk(1),),
        "result": "answer to the prompt",
    }


def test_a_state_without_summaries_gives_empty_ones():
    seen = []

    def make_prompt(chunks, question, totals, summaries, files, last_answer):
        seen.append(summaries)
        return "the prompt", ()

    node = make_respond_node(make_prompt, lambda prompt: "r")

    node({"chunks": (), "question": "why?", "totals": None})

    assert seen == [{"A": "", "B": ""}]


def graph_with(summarize, seen, *, fits=False, plan=None):
    def make_prompt(chunks, question, totals, summaries, files, last_answer):
        seen.append(dict(summaries))
        return "the prompt", chunks[:1]

    return build_graph(
        measure=lambda a, b: SIDES,
        fits=lambda sides, question: fits,
        stuff=lambda sides, question: ((chunk(9),), None),
        make_prompt=make_prompt,
        generate=lambda prompt: "the result",
        search_one=lambda sides, query: (chunk(1),),
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=lambda question, pile: pile,
        plan=plan or (lambda question, a, b: Plan(steps=(), queries=())),
        summarize=summarize,
    )


START = {"question": "why?", "a": "A-1", "b": "B-1"}


def slow_summary(artifact_id):
    time.sleep(0.2)
    return f"summary of {artifact_id}"


def test_respond_waits_for_both_summaries_on_the_search_path():
    seen = []

    graph_with(slow_summary, seen).invoke(START)

    assert seen == [{"A": "summary of A-1", "B": "summary of B-1"}]


def test_respond_waits_for_both_summaries_on_the_stuff_path():
    seen = []

    graph_with(slow_summary, seen, fits=True).invoke(START)

    assert seen == [{"A": "summary of A-1", "B": "summary of B-1"}]


def test_a_graph_without_summarize_gives_respond_empty_summaries():
    seen = []

    graph_with(None, seen).invoke(START)

    assert seen == [{"A": "", "B": ""}]


def test_the_planner_and_the_two_summaries_start_together():
    barrier = threading.Barrier(3, timeout=2)

    def plan(question, a, b):
        barrier.wait()
        return Plan(steps=(), queries=())

    def summarize(artifact_id):
        barrier.wait()
        return f"summary of {artifact_id}"

    seen = []

    graph_with(summarize, seen, plan=plan).invoke(START)

    assert seen == [{"A": "summary of A-1", "B": "summary of B-1"}]
