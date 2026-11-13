"""The full graph, with every optional part switched on, has no node that cannot run.

A node added to `build_graph` and forgotten in an edge is never run and never
fails: the answer is just a little worse, and nothing says why. This runs the
graph in the few scenarios that together reach every node and checks the list of
nodes that ran against the list of nodes the graph has. (The drawn graph is no
help: LangGraph does not draw the conditional edges that have no path map.)
"""

from __future__ import annotations

from labpilot.agent import Correspondence, Plan, Query, build_graph
from labpilot.ingest import Chunk

TWO_FILES = {"question": "q", "a": "A-1", "b": "B-1"}


def chunk(side: str, index: int) -> Chunk:
    return Chunk(
        text="t",
        source="f.py",
        start_line=1,
        end_line=2,
        side=side,
        artifact_id=f"{side}-1",
        chunk_index=index,
    )


def full_graph(*, fits: bool, verdict: str = "PARTIAL", plan: Plan | None = None):
    plan = plan or Plan(
        steps=("find_differences", "find_bugs"),
        queries=(Query("B", "qb"),),
        fresh=True,
    )
    return build_graph(
        measure=lambda a, b: {s: "stored" for s, i in (("A", a), ("B", b)) if i},
        fits=lambda sides, question, last_answer: fits,
        stuff=lambda sides, question: ((chunk("B", 1),), None),
        search_one=lambda sides, query: (chunk(query.side, 7),),
        totals_of=lambda sides: {"A": 5, "B": 6},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: plan,
        make_prompt=lambda chunks, **rest: ("the prompt", chunks),
        generate=lambda prompt: "answer",
        rewrite=lambda question, history, last: question,
        summarize=lambda artifact_id: "summary",
        extract_claims=lambda a: (),
        find_differences=lambda a, b, facts: (),
        find_bugs=lambda artifact, summary: (),
        fresh=lambda question, b: (),
        final_merge=lambda lines: [],
        answer_text=lambda result: "answer",
        gate=lambda sa, sb: Correspondence(verdict, "because"),
        halt_answer=lambda sa, sb, reason: "HALT",
        ask=lambda state: "",
    )


def nodes_that_ran(graph, given) -> set[str]:
    ran = set()
    for event in graph.stream(given, stream_mode="debug"):
        if event["type"] == "task":
            ran.add(event["payload"]["name"])
    return ran


def test_every_node_of_the_full_graph_runs_in_some_scenario():
    searched = full_graph(fits=False)
    scenarios = [
        nodes_that_ran(searched, TWO_FILES),
        nodes_that_ran(full_graph(fits=True), TWO_FILES),
        nodes_that_ran(full_graph(fits=True, verdict="NONE"), TWO_FILES),
    ]

    every = set(searched.get_graph().nodes) - {"__start__", "__end__"}
    ran = set().union(*scenarios)

    assert every - ran == set(), f"these nodes never ran: {sorted(every - ran)}"
    assert ran <= every


def test_a_halt_ends_the_run_before_any_search():
    ran = nodes_that_ran(full_graph(fits=False, verdict="NONE"), TWO_FILES)

    assert "halt" in ran
    assert not ran & {"measure", "search_one", "merge", "respond"}
