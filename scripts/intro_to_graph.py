from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    chunks: list[str]
    answer: str


def search(state: State):
    return {"chunks": ["CLIP_NORM = 1.5", "lr = 3e-4"]}


def write(state: State):
    count = len(state["chunks"])
    return {"answer": f"{state['question']} -> I read {count} chunks"}


builder = StateGraph(State)
builder.add_node("search", search)
builder.add_node("write", write)
builder.add_edge(START, "search")
builder.add_edge("search", "write")
builder.add_edge("write", END)
graph = builder.compile()

start = {"question": "why do results differ?", "chunks": [], "answer": ""}
print(graph.invoke(start))

for step in graph.stream(start, stream_mode="updates"):
    print(step)
