import operator
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send


class State(TypedDict):
    queries: list[str]
    found: Annotated[list[str], operator.add]
    report: str


class OneSearch(TypedDict):
    query: str


def fan_out(state: State) -> list[Send]:
    return [Send("search_one", {"query": q}) for q in state["queries"]]


def search_one(task: OneSearch) -> dict[str, list[str]]:
    time.sleep(1)
    return {"found": ["chunk for " + task["query"]]}


def join(state: State) -> dict[str, str]:
    return {"report": " | ".join(state["found"])}


def build_graph() -> CompiledStateGraph:
    builder = StateGraph(State)
    builder.add_node("search_one", search_one)
    builder.add_node("join", join)
    builder.add_conditional_edges(START, fan_out, ["search_one"])
    builder.add_edge("search_one", "join")
    builder.add_edge("join", END)

    return builder.compile()


graph = build_graph()

for queries in (["lr"], ["lr", "clip", "seed"], ["a", "b", "c", "d", "e"]):
    start = time.perf_counter()
    result = graph.invoke({"queries": queries})
    seconds = time.perf_counter() - start
    print(f"{len(queries)} queries    {seconds:.1f}s   {result['report']}")
