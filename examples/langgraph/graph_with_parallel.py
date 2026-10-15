import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


class State(TypedDict):
    a: str
    b: str
    summary_a: str
    summary_b: str
    report: str


def summarize_a(state: State) -> dict[str, str]:
    time.sleep(1)
    return {"summary_a": "A is about " + state["a"]}


def summarize_b(state: State) -> dict[str, str]:
    time.sleep(1)
    return {"summary_b": "B is about " + state["b"]}


def join(state: State) -> dict[str, str]:
    return {"report": state["summary_a"] + " | " + state["summary_b"]}


def build_graph(parallel: bool) -> CompiledStateGraph:
    builder = StateGraph(State)
    builder.add_node("summarize_a", summarize_a)
    builder.add_node("summarize_b", summarize_b)
    builder.add_node("join", join)
    builder.add_edge(START, "summarize_a")
    if parallel:
        builder.add_edge(START, "summarize_b")
        builder.add_edge(["summarize_a", "summarize_b"], "join")
    else:
        builder.add_edge("summarize_a", "summarize_b")
        builder.add_edge("summarize_b", "join")

    builder.add_edge("join", END)
    return builder.compile()


for parallel in (False, True):
    graph = build_graph(parallel)
    start = time.perf_counter()
    result = graph.invoke({"a": "paper", "b": "code"})
    seconds = time.perf_counter() - start
    print(f"parallel={parallel}    {seconds:.1f}s   {result['report']}")
