from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from labpilot.agent.check_one import NewQuery, make_check_node
from labpilot.agent.claim import Claim
from labpilot.agent.code_finding import CodeFinding
from labpilot.agent.correspondence import Correspondence
from labpilot.agent.extract_claims import make_claims_node, wants_claims
from labpilot.agent.fan_out import fan_out
from labpilot.agent.fan_out_claims import fan_out_claims
from labpilot.agent.find_missing import make_find_missing_node, wants_missing
from labpilot.agent.finding import Finding
from labpilot.agent.gate import make_gate_node
from labpilot.agent.halt import halted, make_halt_node
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
    find_missing: Callable[[str, str], tuple[CodeFinding, ...]] | None = None,
    whole_side: Callable[[Any, str], Chunks | None] | None = None,
    answer_text: Callable[[Any], str] | None = None,
    gate: Callable[[str, str], Correspondence] | None = None,
    halt_answer: Callable[[str, str, str], Any] | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    # The gate reads the two summaries and a halt answers from them, so the three
    # come together or not at all. A half-wired gate is a caller's bug.
    if gate is not None and (summarize is None or halt_answer is None):
        raise ValueError("a gate needs 'summarize' and 'halt_answer'")
    if gate is None and halt_answer is not None:
        raise ValueError("'halt_answer' is only used with a gate")

    def measure_node(state: State) -> dict[str, Any]:
        sides = measure(state["a"], state["b"])
        return {"sides": sides, "fits": fits(sides, state["question"])}

    def stuff_node(state: State) -> dict[str, Any]:
        chunks, totals = stuff(state["sides"], state["question"])
        return {"chunks": chunks, "totals": totals}

    def pick(state: State) -> str | list[Send]:
        return "stuff" if state["fits"] else fan_out(state)

    def after_gate(state: State) -> str:
        return "halt" if halted(state) else "measure"

    def checks_and_scan(state: State) -> str | list[Send]:
        # One fan-out step: a check for each claim and the scan of B run at the
        # same time, and respond runs once, after all of them.
        sends: list[Send] = []
        if extract_claims is not None and check is not None:
            claims = fan_out_claims(state)
            if claims != "respond":
                sends.extend(claims)
        if find_missing is not None and wants_missing(state):
            sends.append(Send("find_missing", {"a": state["a"], "b": state["b"]}))
        return sends or "respond"

    def after_search(state: State) -> str | list[Send]:
        # R21: when everything was read, the answer sees all of both files, and
        # the claims and the scan only cost time. Measured on 2026-10-24: the
        # stuffed answer alone scored 30 of 39 in 35 s; with claims and scan
        # 26 and 28, in 181 and 244 s.
        if state["totals"] is None:
            return "respond"
        if extract_claims is not None and wants_claims(state):
            return "extract_claims"
        return checks_and_scan(state)

    builder = StateGraph(State)
    builder.add_node("plan", make_planner_node(plan))
    builder.add_node("measure", measure_node)
    builder.add_node("stuff", stuff_node)
    builder.add_node("search_one", make_one_search_node(search_one))
    builder.add_node("merge", make_merge_node(totals_of, rank_side, whole_side))
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
    summaries = []
    if summarize is not None:
        for slot in ("a", "b"):
            name = f"summarize_{slot}"
            builder.add_node(name, make_summarize_node(slot, summarize))
            first_steps.append(name)
            summaries.append(name)
    for step in first_steps:
        builder.add_edge(first, step)
    if gate is None:
        builder.add_edge(first_steps, "measure")
    else:
        # The gate waits for both summaries; the planner runs beside them. When
        # the verdict is NONE the run ends with an answer made from the two
        # summaries, and nothing after this point runs (D78 to D80).
        builder.add_node("gate", make_gate_node(gate))
        builder.add_node("halt", make_halt_node(halt_answer))
        builder.add_edge(summaries, "gate")
        builder.add_conditional_edges("gate", after_gate, ["measure", "halt"])
        builder.add_edge("halt", "remember")
    builder.add_conditional_edges("measure", pick)
    builder.add_edge("search_one", "merge")
    # The plan decides which of these run: the claims (and a check for each),
    # and the scan of B for what A does otherwise or never says.
    fanned = ["respond"]
    if extract_claims is not None:
        builder.add_node("extract_claims", make_claims_node(extract_claims))
        fanned.append("extract_claims")
        if check is not None:
            builder.add_node(
                "check_one",
                make_check_node(search_claim or search_one, check, new_query),
            )
            builder.add_edge("check_one", "respond")
    if find_missing is not None:
        builder.add_node("find_missing", make_find_missing_node(find_missing))
        builder.add_edge("find_missing", "respond")
    after_claims = [
        name for name in ("check_one", "find_missing") if name in builder.nodes
    ]
    for searched in ("stuff", "merge"):
        builder.add_conditional_edges(searched, after_search, fanned + after_claims)
    if extract_claims is not None:
        builder.add_conditional_edges(
            "extract_claims", checks_and_scan, ["respond", *after_claims]
        )
    builder.add_edge("respond", "remember")
    builder.add_edge("remember", END)
    return builder.compile(checkpointer=checkpointer)
