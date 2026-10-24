from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from labpilot.agent.check_one import NewQuery, make_check_node
from labpilot.agent.claim import Claim
from labpilot.agent.extract_claims import make_claims_node, wants_claims
from labpilot.agent.fan_out import fan_out
from labpilot.agent.fan_out_claims import fan_out_claims
from labpilot.agent.finding import Finding
from labpilot.agent.merge import make_merge_node
from labpilot.agent.plan import Plan, Query
from labpilot.agent.planner import make_planner_node
from labpilot.agent.remember import make_remember_node
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
    extract_claims: Callable[[str], tuple[Claim, ...]] | None = None,
    check: Callable[[Claim, Chunks], Finding] | None = None,
    search_claim: Callable[[Any, Query], Chunks] | None = None,
    new_query: NewQuery | None = None,
    answer_text: Callable[[Any], str] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    def measure_node(state: State) -> dict[str, Any]:
        sides = measure(state["a"], state["b"])
        return {"sides": sides, "fits": fits(sides, state["question"])}

    def stuff_node(state: State) -> dict[str, Any]:
        chunks, totals = stuff(state["sides"], state["question"])
        return {"chunks": chunks, "totals": totals}

    def pick(state: State) -> str | list[Send]:
        return "stuff" if state["fits"] else fan_out(state)

    def after_search(state: State) -> str:
        return "extract_claims" if wants_claims(state) else "respond"

    builder = StateGraph(State)
    builder.add_node("plan", make_planner_node(plan))
    builder.add_node("measure", measure_node)
    builder.add_node("stuff", stuff_node)
    builder.add_node("search_one", make_one_search_node(search_one))
    builder.add_node("merge", make_merge_node(totals_of, rank_side))
    builder.add_node("respond", make_respond_node(make_prompt, generate))
    builder.add_node("remember", make_remember_node(answer_text))

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
    builder.add_edge("search_one", "merge")
    if extract_claims is None:
        builder.add_edge("stuff", "respond")
        builder.add_edge("merge", "respond")
    else:
        # The plan decides: the claims step runs only when the planner listed it.
        builder.add_node("extract_claims", make_claims_node(extract_claims))
        for searched in ("stuff", "merge"):
            builder.add_conditional_edges(
                searched, after_search, ["extract_claims", "respond"]
            )
        if check is None:
            builder.add_edge("extract_claims", "respond")
        else:
            # One check for each claim, all at the same time. With no claims
            # the path function sends the run straight to respond.
            builder.add_node(
                "check_one",
                make_check_node(search_claim or search_one, check, new_query),
            )
            builder.add_conditional_edges(
                "extract_claims", fan_out_claims, ["check_one", "respond"]
            )
            builder.add_edge("check_one", "respond")
    builder.add_edge("respond", "remember")
    builder.add_edge("remember", END)
    return builder.compile(checkpointer=checkpointer)
