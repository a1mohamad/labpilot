import operator
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    question: str
    history: Annotated[list[str], operator.add]
    answer: str


def respond(state: State):
    seen = len(state["history"])
    return {
        "answer": f"{state['question']} i have seen {seen} messages so far",
        "history": [state["question"]],
    }


builder = StateGraph(State)
builder.add_node("respond", respond)
builder.add_edge(START, "respond")
builder.add_edge("respond", END)
graph = builder.compile(checkpointer=InMemorySaver())

chat7 = {"configurable": {"thread_id": "chat-7"}}
chat8 = {"configurable": {"thread_id": "chat-8"}}

print(graph.invoke({"question": "why do the results differ?"}, chat7))
print(graph.invoke({"question": "so what about the learning rate?"}, chat7))
print(graph.invoke({"question": "hello?"}, chat8))
print(graph.get_state(chat7))
