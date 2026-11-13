from langgraph.types import Send

from labpilot.agent.plan_check import present_sides, question_queries
from labpilot.agent.state import State


def fan_out(state: State) -> list[Send]:
    sides = present_sides(state["a"], state["b"])
    about = state["plan"].about
    # A question about one of two files searches that file only (D105).
    if about in sides:
        sides = (about,)
    asked = question_queries(state["question"], sides)
    queries = asked + tuple(q for q in state["plan"].queries if q not in asked)
    if not queries:
        raise ValueError("nothing to search: no side has a file")

    return [
        Send(
            "search_one",
            {"sides": {query.side: state["sides"][query.side]}, "query": query},
        )
        for query in queries
    ]
