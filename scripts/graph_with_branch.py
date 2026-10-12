from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    size: int
    fits: bool
    chunks: list[str]
    answer: str


def build_graph(*, fits, stuff, search, generate):
    def empty_node(state: State):
        return {"answer": "please ask a question"}

    def check_node(state: State):
        return {"fits": fits(state["size"])}

    def stuff_node(state: State):
        return {"chunks": stuff(state["question"])}

    def search_node(state: State):
        return {"chunks": search(state["question"])}

    def answer_node(state: State):
        return {"answer": generate(state["question"], state["chunks"])}

    def pick(state: State):
        if not state["question"].strip():
            return "empty"
        return "stuff" if state["fits"] else "search"

    builder = StateGraph(State)
    builder.add_node("check", check_node)
    builder.add_node("stuff", stuff_node)
    builder.add_node("search", search_node)
    builder.add_node("answer", answer_node)
    builder.add_node("empty", empty_node)
    builder.add_edge(START, "check")
    builder.add_conditional_edges("check", pick)
    builder.add_edge("stuff", "answer")
    builder.add_edge("search", "answer")
    builder.add_edge("empty", END)
    builder.add_edge("answer", END)
    return builder.compile()


def fake_fits(size):
    return size <= 50


def fake_stuff(question):
    return ["chunk 1", "chunk 2", "chunk 3"]


def fake_search(question):
    return ["chunk about the learning rate", "chunk about clip norm"]


def fake_generate(question, chunks):
    return f"{question} -> I read {len(chunks)} chunks"


graph = build_graph(
    fits=fake_fits, stuff=fake_stuff, search=fake_search, generate=fake_generate
)


for size in (10, 500):
    print("size\t", size)
    for update in graph.stream(
        {"question": "why the results differ?", "size": size}, stream_mode="updates"
    ):
        print("\t", update)

for question in ("", "   "):
    print(repr(question))
    for update in graph.stream(
        {"question": question, "size": 10}, stream_mode="updates"
    ):
        print("\t", update)
