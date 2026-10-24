from collections.abc import Callable
from typing import Any

from labpilot.agent.plan_check import present_sides
from labpilot.agent.state import Chunks, State


def make_respond_node(
    make_prompt: Callable[..., tuple[str, Chunks]],
    generate: Callable[[str], Any],
) -> Callable[[State], dict[str, Any]]:
    def respond_node(state: State) -> dict[str, Any]:
        summaries = {"A": state.get("summary_a", ""), "B": state.get("summary_b", "")}
        files = len(present_sides(state.get("a", ""), state.get("b", "")))
        # Handed over only when there are some, so a graph with no checks calls
        # make_prompt exactly as it did before the checks existed.
        findings = state.get("findings", ())
        checked = {"findings": findings} if findings else {}
        code_findings = state.get("code_findings", ())
        if code_findings:
            checked["code_findings"] = code_findings
        prompt, selected = make_prompt(
            state["chunks"],
            question=state["question"],
            totals=state["totals"],
            summaries=summaries,
            files=files,
            last_answer=state.get("last_answer", ""),
            **checked,
        )
        return {"prompt": prompt, "selected": selected, "result": generate(prompt)}

    return respond_node
