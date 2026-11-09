import logging
import threading

from langgraph.checkpoint.memory import InMemorySaver

from labpilot.agent import (
    Bug,
    BugsError,
    Plan,
    Query,
    allowed_steps,
    build_graph,
)
from labpilot.agent.find_bugs import STEP, bugs_task, make_find_bugs_node, wants_bugs
from labpilot.ingest import Chunk

SOURCES = ["[train.py · def step · lines 1-9]", "[train.py · def eval · lines 10-19]"]


HUNT = Plan(steps=(STEP,), queries=(Query("B", "bugs"),))


NO_HUNT = Plan(steps=("summarize",), queries=(Query("B", "bugs"),))


def bug(text="beta1 is used for the second moment", verdict="unchecked"):
    return Bug("logic", text, SOURCES[0], "beta1**step", "high", verdict)


def chunk(index):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
    )


def run(plan, *, find, fits_value=False, differences=None, claims=(), saver=None):
    seen = []

    def make_prompt(chunks, **kwargs):
        seen.append(kwargs)
        return "the prompt", chunks

    graph = build_graph(
        measure=lambda a, b: {"A": "stored A", "B": "stored B"},
        fits=lambda sides, question: fits_value,
        stuff=lambda sides, question: ((chunk(0),), None),
        search_one=lambda sides, query: (chunk(1),),
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: plan,
        make_prompt=make_prompt,
        generate=lambda prompt: "the result",
        extract_claims=lambda a: claims,
        find_differences=differences,
        find_bugs=find,
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "chat"}} if saver else None
    final = graph.invoke({"question": "bugs?", "a": "A-1", "b": "B-1"}, config)
    return final, seen


def test_the_step_is_allowed_only_when_b_has_a_file():
    # D106: A is the reference the person trusts, so it is never hunted.
    assert STEP in allowed_steps(("B",))
    assert STEP not in allowed_steps(("A",))
    assert STEP in allowed_steps(("A", "B"))
    assert STEP not in allowed_steps(())
    assert wants_bugs({"plan": HUNT}) and not wants_bugs({"plan": NO_HUNT})


def test_only_b_is_hunted_and_a_alone_is_never_hunted():
    two = {"a": "A-1", "b": "B-1", "summary_a": "paper", "summary_b": "code"}

    assert bugs_task(two) == {"artifact": "B-1", "summary": "code"}
    assert bugs_task({"a": "", "b": "B-1", "summary_b": "code"}) == {
        "artifact": "B-1",
        "summary": "code",
    }
    assert bugs_task({"a": "A-1", "b": "", "summary_a": "paper"}) is None
    assert bugs_task({"a": "", "b": ""}) is None


def test_a_failed_hunt_gives_no_bugs_and_logs_why(caplog):
    def broken(artifact, summary):
        raise BugsError("no tier")

    with caplog.at_level(logging.WARNING):
        got = make_find_bugs_node(broken)({"artifact": "B-1", "summary": ""})

    assert got == {"bugs": []}
    assert "no tier" in caplog.text


def test_the_hunt_runs_on_the_stuffed_path_too():
    # Unlike the differences: one call over a whole file found about
    # half the bugs the hunt finds (2026-10-31).
    _, seen = run(HUNT, find=lambda artifact, summary: (bug(),), fits_value=True)

    assert seen[0]["bugs"] == [bug()]


def test_the_hunt_runs_on_the_search_path():
    _, seen = run(HUNT, find=lambda artifact, summary: (bug(),))

    assert seen[0]["bugs"] == [bug()]


def test_a_plan_without_the_step_never_hunts():
    def find(artifact, summary):
        raise AssertionError("not planned")

    _, seen = run(NO_HUNT, find=find, fits_value=True)

    assert "bugs" not in seen[0]


def test_the_hunt_and_the_differences_run_together_and_respond_runs_once():
    from labpilot.agent import Claim, Difference

    barrier = threading.Barrier(2, timeout=5)
    found = Difference("differs", "B uses 64", "[s]", "batch = 64")

    def differences(a, b, facts):
        barrier.wait()
        return (found,)

    def find(artifact, summary):
        barrier.wait()
        return (bug(),)

    plan = Plan(steps=("find_differences", STEP), queries=(Query("B", "x"),))
    claim = Claim("the batch is 128", "[paper.md]", "q")
    _, seen = run(plan, find=find, differences=differences, claims=(claim,))

    assert len(seen) == 1
    assert seen[0]["bugs"] == [bug()]
    assert seen[0]["differences"] == [found]


def test_the_bugs_of_one_message_do_not_pile_up_in_the_next():
    saver = InMemorySaver()
    run(HUNT, find=lambda a, s: (bug("first"),), saver=saver)
    final, seen = run(HUNT, find=lambda a, s: (bug("second"),), saver=saver)

    assert seen[0]["bugs"] == [bug("second")]
    assert final["bugs"] == []
