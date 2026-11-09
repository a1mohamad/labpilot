from collections.abc import Callable, Mapping
from typing import Any

from langgraph.types import Overwrite

from labpilot.agent.state import State

Merge = Callable[[Mapping[int, str]], list[list[int]]]

# A line is cut at this length for the merge: the point, not every detail.
LINE_CHARS = 300


def make_final_merge_node(merge: Merge) -> Callable[[State], dict[str, Any]]:
    """A point found by both nodes is shown once, as the difference (D100).

    The difference also says what A states, so it tells the answer more than a
    bug line about the same code. A group of bugs alone changes nothing here:
    the bug finder already merged its own repeats.
    """

    def final_merge_node(state: State) -> dict[str, Any]:
        differences = state.get("differences", ())
        bugs = state.get("bugs", ())
        if not differences or not bugs:
            return {}

        count = len(differences)
        lines = {n: item.text[:LINE_CHARS] for n, item in enumerate(differences)}
        lines |= {count + n: bug.text[:LINE_CHARS] for n, bug in enumerate(bugs)}
        hidden: set[int] = set()
        for group in merge(lines):
            if any(n < count for n in group):
                hidden |= {n - count for n in group if n >= count}
        if not hidden:
            return {}
        kept = [bug for n, bug in enumerate(bugs) if n not in hidden]
        return {"bugs": Overwrite(kept)}

    return final_merge_node
