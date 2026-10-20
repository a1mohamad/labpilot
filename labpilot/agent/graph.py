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
from labpilot.agent.search_one import make_one_search_node
from labpilot.agent.state import Chunks, State, Totals
from labpilot.agent.summarize import make_summarize_node


def build_graph(
    *,
    measure: Callable[[str, str], Any],
    fits: Callable[[Any, str], bool],
    stuff: Callable[[Any, str], tuple[Chunks, Totals]],
    search: Callable[[Any, str], tuple[Chunks, Totals]] | None = None,
    search_one: Callable[[Any, Query], Chunks] | None = None,
    totals_of: Callable[[Any], Totals] | None = None,
    rank_side: Callable[[str, Chunks], Chunks] | None = None,
    make_prompt: Callable[[Chunks, str, Totals], tuple[str, Chunks]],
    generate: Callable[[str], Any],
    summarize: Callable[[str], str] | None = None,
    plan: Callable[[str, str, str], Plan] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    if (search is None) == (search_one is None):
        raise ValueError("give exactly one of search and search one")
    if search_one is not None and None in (plan, totals_of, rank_side):
        raise ValueError("search_one needs plan, totals_of and rank_side too")

    def measure_node(state: State) -> dict[str, Any]:
        sides = measure(state["a"], state["b"])
        return {"sides": sides, "fits": fits(sides, state["question"])}

    def stuff_node(state: State) -> dict[str, Any]:
        chunks, totals = stuff(state["sides"], state["question"])
        return {"chunks": chunks, "totals": totals}

    def search_node(state: State) -> dict[str, Any]:
        chunks, totals = search(state["sides"], state["question"])
        return {"chunks": chunks, "totals": totals}

    def prompt_node(state: State) -> dict[str, Any]:
        prompt, selected = make_prompt(
            state["chunks"], state["question"], state["totals"]
        )
        return {"prompt": prompt, "selected": selected}

    def generate_node(state: State) -> dict[str, Any]:
        return {"result": generate(state["prompt"])}

    def remember_node(state: State) -> dict[str, Any]:
        return {"history": [state["question"]]}

    def pick(state: State) -> str | list[Send]:
        if state["fits"]:
            return "stuff"
        return "search" if search_one is None else fan_out(state)

    builder = StateGraph(State)
    builder.add_node("measure", measure_node)
    builder.add_node("stuff", stuff_node)
    builder.add_node("prompt", prompt_node)
    builder.add_node("generate", generate_node)
    builder.add_node("remember", remember_node)
    if search_one is None:
        builder.add_node("search", search_node)
        builder.add_edge("search", "prompt")
    else:
        builder.add_node("search_one", make_one_search_node(search_one))
        builder.add_node("merge", make_merge_node(totals_of, rank_side))
        builder.add_edge("search_one", "merge")
        builder.add_edge("merge", "prompt")
    first = "measure"
    if plan is not None:
        builder.add_node("plan", make_planner_node(plan))
        builder.add_edge("plan", "measure")
        first = "plan"
    builder.add_edge(START, first)
    if summarize is not None:
        for slot in ("a", "b"):
            name = f"summarize_{slot}"
            builder.add_node(name, make_summarize_node(slot, summarize))
            builder.add_edge(START, name)
            builder.add_edge(name, END)
    builder.add_conditional_edges("measure", pick)
    builder.add_edge("stuff", "prompt")
    builder.add_edge("prompt", "generate")
    builder.add_edge("generate", "remember")
    builder.add_edge("remember", END)
    return builder.compile(checkpointer=checkpointer)
