"""Which node runs next: the choices on the edges of the graph.

Each one reads the state and answers with a node name, or with the nodes to
start at the same time. `build_graph` draws the edges, and nothing here calls a
model.
"""

from dataclasses import dataclass

from langgraph.types import Send

from labpilot.agent.fan_out import fan_out
from labpilot.agent.find_bugs import bugs_task, wants_bugs
from labpilot.agent.find_differences import differences_task, wants_differences
from labpilot.agent.fresh import fresh_task, wants_fresh
from labpilot.agent.halt import halted
from labpilot.agent.state import State


def after_measure(state: State) -> str | list[Send]:
    if not state["plan"].files:
        return "respond"
    return "stuff" if state["fits"] else fan_out(state)


def after_gate(state: State) -> str:
    return "halt" if halted(state) else "measure"


@dataclass(frozen=True, slots=True)
class FinderChoices:
    """The choices after the search, for the finders this graph was given."""

    claims: bool
    differences: bool
    bugs: bool
    fresh: bool

    def names(self) -> list[str]:
        wired = {
            "find_differences": self.differences,
            "find_bugs": self.bugs,
            "fresh": self.fresh,
        }
        return [name for name, is_wired in wired.items() if is_wired]

    def bug_hunt(self, state: State) -> list[Send]:
        task = bugs_task(state) if self.bugs else None
        if task is None or not wants_bugs(state):
            return []
        return [Send("find_bugs", task)]

    def new_check(self, state: State) -> list[Send]:
        # D107: a question the first analysis did not cover gets ONE new check.
        if not self.fresh or not wants_fresh(state):
            return []
        return [Send("fresh", fresh_task(state))]

    def finders(self, state: State) -> str | list[Send]:
        # The differences and the bug hunt run at the same time, and the next
        # node runs once, after both of them.
        sends = self.bug_hunt(state) + self.new_check(state)
        if self.differences and wants_differences(state):
            sends.append(Send("find_differences", differences_task(state)))
        return sends or "respond"

    def after_search(self, state: State) -> str | list[Send]:
        # R21: when everything was read, the answer sees all of both files, and
        # the claims and the differences only cost time (measured 2026-10-24:
        # the stuffed answer alone scored 30 of 39 in 35 s). The bug hunt still
        # runs: one call over a whole file found about half of what the hunt
        # finds (section 29).
        if state["totals"] is None:
            return self.bug_hunt(state) + self.new_check(state) or "respond"
        if self.claims and wants_differences(state):
            return "extract_claims"
        return self.finders(state)
