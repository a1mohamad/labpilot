from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

runs = {"read_files": 0, "respond": 0}


class State(TypedDict):
    question: str
    notes: str
    answer: str


def read_files(state: State):
    runs["read_files"] += 1
    return {"notes": "files read"}


def respond(state: State):
    runs["respond"] += 1
    reply = interrupt("Which split did you tune the threshold on?")
    if reply == "":
        return {"answer": f"{state['question']} -> answered without your help"}
    return {"answer": f"{state['question']} -> you said: {reply}"}


builder = StateGraph(State)
builder.add_node("read_files", read_files)
builder.add_node("respond", respond)
builder.add_edge(START, "read_files")
builder.add_edge(START, "respond")
builder.add_edge("read_files", END)
builder.add_edge("respond", END)
graph = builder.compile(checkpointer=InMemorySaver())


chat1 = {"configurable": {"thread_id": "chat-1"}}
chat2 = {"configurable": {"thread_id": "chat-2"}}


print("1", graph.invoke({"question": "why is my F1 lower?"}, chat1))
print("  next node:", graph.get_state(chat1).next)
print("2", graph.invoke(Command(resume="validation"), chat1))
print("  runs:", runs)


print(graph.invoke({"question": "and the loss?"}, chat2))
print("3", graph.invoke(Command(resume=""), chat2))
