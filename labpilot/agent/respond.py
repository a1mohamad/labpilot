from collections.abc import Callable, Sequence
from typing import Any

from labpilot.agent.code_finding import A_SILENT, CodeFinding
from labpilot.agent.finding import Finding
from labpilot.agent.plan_check import present_sides
from labpilot.agent.state import Chunks, State
from labpilot.ingest import Chunk


def deciding_parts(
    findings: Sequence[Finding], code_findings: Sequence[CodeFinding]
) -> Chunks:
    """The parts behind the findings, most telling first, each once.

    A mismatch first, then what B does differently from A, then what A never
    says, so a part that is cut for room is the least telling one.
    """
    ordered: list[Chunk | None] = [
        f.evidence for f in findings if f.verdict == "mismatch"
    ]
    ordered += [c.evidence for c in code_findings if c.a_says != A_SILENT]
    ordered += [c.evidence for c in code_findings if c.a_says == A_SILENT]
    picked: dict[tuple[str, int], Chunk] = {}
    for chunk in ordered:
        if chunk is not None:
            picked.setdefault((chunk.artifact_id, chunk.chunk_index), chunk)
    return tuple(picked.values())


def with_parts(chunks: Chunks, extra: Sequence[Chunk]) -> Chunks:
    """`chunks`, then each part of `extra` they do not hold yet, at the END.

    The ids of a prompt are numbered on this list, and the page resolves the
    citations against the same list. A deciding part put in FRONT would shift
    every id, so `B-8` would point at another part (found 2026-10-24: only 8
    of 19 citations resolved).
    """
    if not extra:
        return chunks
    held = {(chunk.artifact_id, chunk.chunk_index) for chunk in chunks}
    added = [c for c in extra if (c.artifact_id, c.chunk_index) not in held]
    return (*chunks, *added) if added else chunks


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
        # The parts that decided a mismatch or show a code finding, so the
        # answer reads the code itself and not only one quoted line (R20).
        evidence = deciding_parts(findings, code_findings)
        if evidence:
            checked["evidence"] = evidence
        chunks = with_parts(state["chunks"], evidence)
        prompt, selected = make_prompt(
            chunks,
            question=state["question"],
            totals=state["totals"],
            summaries=summaries,
            files=files,
            last_answer=state.get("last_answer", ""),
            **checked,
        )
        out = {"prompt": prompt, "selected": selected, "result": generate(prompt)}
        if chunks is not state["chunks"]:
            out["chunks"] = chunks
        return out

    return respond_node
