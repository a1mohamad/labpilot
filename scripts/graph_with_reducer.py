import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    findings: Annotated[list[str], operator.add]


def check_clip(state: State):
    return {"findings": ["CLIP_NORM: code 1.5, paper 1.0 -> mismatch"]}


def check_lr(state: State):
    return {"findings": ["lr: 3e-4 -> match"]}


builder = StateGraph(State)
builder.add_node("check_clip", check_clip)
builder.add_node("check_lr", check_lr)
builder.add_edge(START, "check_clip")
builder.add_edge("check_clip", "check_lr")
builder.add_edge("check_lr", END)
graph = builder.compile()

print(graph.invoke({"findings": []}))

builder = StateGraph(State)
builder.add_node("check_clip", check_clip)
builder.add_node("check_lr", check_lr)
builder.add_edge(START, "check_clip")
builder.add_edge(START, "check_lr")
builder.add_edge("check_clip", END)
builder.add_edge("check_lr", END)
graph = builder.compile()

print(graph.invoke({"findings": []}))
