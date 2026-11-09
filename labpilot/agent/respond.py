from collections.abc import Callable, Sequence
from typing import Any

from labpilot.agent.bug import REAL, Bug
from labpilot.agent.difference import SILENT, Difference
from labpilot.agent.plan_check import present_sides
from labpilot.agent.state import Chunks, State
from labpilot.ingest import Chunk


def deciding_parts(differences: Sequence[Difference], bugs: Sequence[Bug]) -> Chunks:
    """The parts behind the findings, most telling first, each once.

    What B does differently from A or leaves out and a real bug first, then what
    A never says and the other bugs, so a part that is cut for room is the least
    telling one.
    """
    ordered: list[Chunk | None] = [
        d.evidence for d in differences if d.kind != SILENT and not d.unclear
    ]
    ordered += [b.evidence for b in bugs if b.verdict == REAL]
    ordered += [d.evidence for d in differences if d.kind == SILENT or d.unclear]
    ordered += [b.evidence for b in bugs if b.verdict != REAL]
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
        sides = present_sides(state.get("a", ""), state.get("b", ""))
        files = len(sides)
        differences = state.get("differences", ())
        bugs = state.get("bugs", ())
        # The parts that show a finding, so the answer reads the code itself
        # and not only one quoted line (R20).
        evidence = deciding_parts(differences, bugs)
        chunks = with_parts(state["chunks"], evidence)
        prompt, selected = make_prompt(
            chunks,
            question=state["question"],
            totals=state["totals"],
            summaries=summaries,
            files=files,
            last_answer=state.get("last_answer", ""),
            differences=differences,
            bugs=bugs,
            evidence=evidence,
            # A alone is the reference the person trusts: explained, not
            # checked (D106).
            reference=sides == ("A",),
        )
        out = {"prompt": prompt, "selected": selected, "result": generate(prompt)}
        if chunks is not state["chunks"]:
            out["chunks"] = chunks
        return out

    return respond_node
