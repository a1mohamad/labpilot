from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from labpilot.agent.fan_out import fan_out
from labpilot.agent.merge import make_merge_node
from labpilot.agent.plan import Plan, Query
from labpilot.agent.planner import make_planner_node
from labpilot.agent.respond import make_respond_node
from labpilot.agent.rewrite import make_rewrite_node
from labpilot.agent.search_one import make_one_search_node
from labpilot.agent.state import Chunks, State, Totals
from labpilot.agent.summarize import make_summarize_node


def build_graph(
    *,
    measure: Callable[[str, str], Any],
    fits: Callable[[Any, str], bool],
    stuff: Callable[[Any, str], tuple[Chunks, Totals]],
    search_one: Callable[[Any, Query], Chunks],
    totals_of: Callable[[Any], Totals],
    rank_side: Callable[[str, Chunks], Chunks],
    plan: Callable[[str, str, str], Plan],
    make_prompt: Callable[..., tuple[str, Chunks]],
    generate: Callable[[str], Any],
    rewrite: Callable[[str, list[str], str], str] | None = None,
    summarize: Callable[[str], str] | None = None,
    answer_text: Callable[[Any], str] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    def measure_node(state: State) -> dict[str, Any]:
        sides = measure(state["a"], state["b"])
        return {"sides": sides, "fits": fits(sides, state["question"])}

    def stuff_node(state: State) -> dict[str, Any]:
        chunks, totals = stuff(state["sides"], state["question"])
        return {"chunks": chunks, "totals": totals}

    def remember_node(state: State) -> dict[str, Any]:
        remembered: dict[str, Any] = {"history": [state["question"]]}
        if answer_text is not None:
            remembered["last_answer"] = answer_text(state["result"])
        return remembered

    def pick(state: State) -> str | list[Send]:
        return "stuff" if state["fits"] else fan_out(state)

    builder = StateGraph(State)
    builder.add_node("plan", make_planner_node(plan))
    builder.add_node("measure", measure_node)
    builder.add_node("stuff", stuff_node)
    builder.add_node("search_one", make_one_search_node(search_one))
    builder.add_node("merge", make_merge_node(totals_of, rank_side))
    builder.add_node("respond", make_respond_node(make_prompt, generate))
    builder.add_node("remember", remember_node)

    # A follow-up is rewritten first, so the planner, the searches, the rerank
    # and the answer all read the standalone question.
    first = START
    if rewrite is not None:
        builder.add_node("rewrite", make_rewrite_node(rewrite))
        builder.add_edge(first, "rewrite")
        first = "rewrite"
    # The planner and the two summaries start together, and measure waits for
    # all of them, so respond can read the summaries whichever way it was reached.
    first_steps = ["plan"]
    if summarize is not None:
        for slot in ("a", "b"):
            name = f"summarize_{slot}"
            builder.add_node(name, make_summarize_node(slot, summarize))
            first_steps.append(name)
    for step in first_steps:
        builder.add_edge(first, step)
    builder.add_edge(first_steps, "measure")
    builder.add_conditional_edges("measure", pick)
    builder.add_edge("stuff", "respond")
    builder.add_edge("search_one", "merge")
    builder.add_edge("merge", "respond")
    builder.add_edge("respond", "remember")
    builder.add_edge("remember", END)
    return builder.compile(checkpointer=checkpointer)
