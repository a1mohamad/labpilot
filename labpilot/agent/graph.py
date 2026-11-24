from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from labpilot.agent.choices import FinderChoices, after_gate, after_measure
from labpilot.agent.claim import Claim
from labpilot.agent.correspondence import Correspondence
from labpilot.agent.extract_claims import make_claims_node
from labpilot.agent.final_merge import Merge, make_final_merge_node
from labpilot.agent.find_bugs import FindBugs, make_find_bugs_node
from labpilot.agent.find_differences import (
    FindDifferences,
    make_find_differences_node,
)
from labpilot.agent.fresh import FreshCheck, make_fresh_node
from labpilot.agent.gate import make_gate_node
from labpilot.agent.halt import make_halt_node
from labpilot.agent.measure import make_measure_node, make_stuff_node
from labpilot.agent.merge import make_merge_node
from labpilot.agent.plan import Plan, Query
from labpilot.agent.planner import make_planner_node
from labpilot.agent.remember import make_remember_node
from labpilot.agent.respond import make_respond_node
from labpilot.agent.rewrite import make_rewrite_node
from labpilot.agent.search_one import make_one_search_node
from labpilot.agent.state import Chunks, State, Totals
from labpilot.agent.summarize import make_summarize_node
from labpilot.timing import timed


def build_graph(
    *,
    measure: Callable[[str, str], Any],
    fits: Callable[[Any, str, str], bool],
    stuff: Callable[[Any, str], tuple[Chunks, Totals]],
    search_one: Callable[[Any, Query], Chunks],
    totals_of: Callable[[Any], Totals],
    rank_side: Callable[[str, Chunks], Chunks],
    plan: Callable[[str, str, str], Plan],
    make_prompt: Callable[..., tuple[str, Chunks]],
    generate: Callable[[str], Any],
    generate_for_files: Callable[[int], Callable[[str], Any]] | None = None,
    rewrite: Callable[[str, list[str], str], str] | None = None,
    summarize: Callable[[str], str] | None = None,
    extract_claims: Callable[[str], tuple[Claim, ...]] | None = None,
    find_differences: FindDifferences | None = None,
    find_bugs: FindBugs | None = None,
    fresh: FreshCheck | None = None,
    final_merge: Merge | None = None,
    whole_side: Callable[[Any, str], Chunks | None] | None = None,
    answer_text: Callable[[Any], str] | None = None,
    gate: Callable[[str, str, str, str], Correspondence] | None = None,
    halt_answer: Callable[[str, str, str], Any] | None = None,
    ask: Callable[[State], str] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    # The gate reads the two summaries and a halt answers from them, so the three
    # come together or not at all. A half-wired gate is a caller's bug.
    if gate is not None and (summarize is None or halt_answer is None):
        raise ValueError("a gate needs 'summarize' and 'halt_answer'")
    if gate is None and halt_answer is not None:
        raise ValueError("'halt_answer' is only used with a gate")

    choices = FinderChoices(
        claims=extract_claims is not None,
        differences=find_differences is not None,
        bugs=find_bugs is not None,
        fresh=fresh is not None,
    )
    builder = StateGraph(State)
    _add(builder, "plan", make_planner_node(plan))
    _add(builder, "measure", make_measure_node(measure, fits))
    _add(builder, "stuff", make_stuff_node(stuff))
    _add(builder, "search_one", make_one_search_node(search_one))
    _add(builder, "merge", make_merge_node(totals_of, rank_side, whole_side))
    _add(
        builder,
        "respond",
        make_respond_node(make_prompt, generate, ask, generate_for_files),
    )
    _add(builder, "remember", make_remember_node(answer_text))

    _wire_start(builder, rewrite, summarize, gate, halt_answer)
    builder.add_conditional_edges("measure", after_measure)
    builder.add_edge("search_one", "merge")
    if find_differences is not None:
        node = make_find_differences_node(find_differences)
        _add(builder, "find_differences", node)
    if find_bugs is not None:
        _add(builder, "find_bugs", make_find_bugs_node(find_bugs))
    if fresh is not None:
        _add(builder, "fresh", make_fresh_node(fresh))
    _wire_finders(builder, choices, final_merge, extract_claims)
    builder.add_edge("respond", "remember")
    builder.add_edge("remember", END)
    return builder.compile(checkpointer=checkpointer)


def _add(builder: StateGraph, name: str, node: Callable[..., Any]) -> None:
    # Every node reports its own seconds (S1), and names itself for the model
    # calls it makes.
    builder.add_node(name, timed(name, node))


def _wire_start(
    builder: StateGraph,
    rewrite: Callable[[str, list[str], str], str] | None,
    summarize: Callable[[str], str] | None,
    gate: Callable[[str, str, str, str], Correspondence] | None,
    halt_answer: Callable[[str, str, str], Any] | None,
) -> None:
    """Everything before `measure`: rewrite, plan, the two summaries, the gate."""
    # A follow-up is rewritten first, so the planner, the searches, the rerank
    # and the answer all read the standalone question.
    first = START
    if rewrite is not None:
        _add(builder, "rewrite", make_rewrite_node(rewrite))
        builder.add_edge(first, "rewrite")
        first = "rewrite"

    # The planner and the two summaries start together, and measure waits for
    # all of them, so respond can read the summaries whichever way it was reached.
    summaries = []
    if summarize is not None:
        for slot in ("a", "b"):
            name = f"summarize_{slot}"
            _add(builder, name, make_summarize_node(slot, summarize))
            summaries.append(name)
    first_steps = ["plan", *summaries]
    for step in first_steps:
        builder.add_edge(first, step)

    if gate is None:
        builder.add_edge(first_steps, "measure")
        return
    # The gate waits for both summaries; the planner runs beside them. When the
    # verdict is NONE the run ends with an answer made from the two summaries,
    # and nothing after this point runs (D78 to D80).
    _add(builder, "gate", make_gate_node(gate))
    _add(builder, "halt", make_halt_node(halt_answer))
    builder.add_edge(summaries, "gate")
    builder.add_conditional_edges("gate", after_gate, ["measure", "halt"])
    builder.add_edge("halt", "remember")


def _wire_finders(
    builder: StateGraph,
    choices: FinderChoices,
    final_merge: Merge | None,
    extract_claims: Callable[[str], tuple[Claim, ...]] | None,
) -> None:
    """From the search to the answer: the claims, the finders, the last merge.

    The plan decides which finders run: the differences between A and B (after
    the claims, which give it A's facts) and the bugs of one file.
    """
    # Where the finders lead: the last cheap merge when there is one.
    after_finders = "respond"
    if final_merge is not None:
        _add(builder, "final_merge", make_final_merge_node(final_merge))
        builder.add_edge("final_merge", "respond")
        after_finders = "final_merge"

    found_by = choices.names()
    for name in found_by:
        builder.add_edge(name, after_finders)

    after = ["respond", *found_by]
    if extract_claims is not None:
        _add(builder, "extract_claims", make_claims_node(extract_claims))
        builder.add_conditional_edges("extract_claims", choices.finders, after)
        after = [*after, "extract_claims"]
    for searched in ("stuff", "merge"):
        builder.add_conditional_edges(searched, choices.after_search, after)
