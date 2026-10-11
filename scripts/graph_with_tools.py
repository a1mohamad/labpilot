from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    chunks: list[str]
    answer: str


def build_graph(search, generate):
    def search_node(state: State):
        return {"chunks": search(state["question"])}

    def answer_node(state: State):
        return {"answer": generate(state["question"], state["chunks"])}

    builder = StateGraph(State)
    builder.add_node("search", search_node)
    builder.add_node("answer", answer_node)
    builder.add_edge(START, "search")
    builder.add_edge("search", "answer")
    builder.add_edge("answer", END)
    return builder.compile()


def fake_search(question):
    return ["chunk about learning rate", "chunk about clipping"]


def fake_answer(question, chunks):
    return f"{question} -> I read {len(chunks)} chunks"


graph = build_graph(fake_search, fake_answer)
print(graph.invoke({"question": "why do results differ"}))
