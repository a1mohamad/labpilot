from collections.abc import Callable
from typing import Any, TypedDict

from labpilot.agent.plan import Query
from labpilot.agent.state import Chunks


class OneSearch(TypedDict):
    sides: Any
    query: Query


def make_one_search_node(
    search_one: Callable[[Any, Query], Chunks],
) -> Callable[[OneSearch], dict[str, list[Chunks]]]:
    def search_one_node(task: OneSearch) -> dict[str, list[Chunks]]:
        return {"found": [search_one(task["sides"], task["query"])]}

    return search_one_node
