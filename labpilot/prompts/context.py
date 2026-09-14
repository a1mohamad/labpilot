from __future__ import annotations

from labpilot.ingest import Chunk
from labpilot.prompts._ids import assign_ids
from labpilot.tokens import estimate_tokens

SIDES = ("A", "B")
INCLUDED = "text included"
DROPPED = "text NOT included"
NOTHING_SENT = "(no part of this side was included)"

# How much of the prompt the table of contents may spend before it degrades.
#
# MEASURED 2026-09-14 on labpilot/ alone - 410 chunks in 94 files - a per-chunk
# outline costs 10,592 tokens of a 26,000 budget. 41% before one line of
# evidence, and CLAUDE.md's worst recorded case is 210,541. So the outline
# needs a ceiling of its own, or it crowds out the thing it describes.
#
# 4,000 is about 15% of PROMPT_BUDGET and IS A GUESS, labelled like
# WARN_MINUTES. Slice 8 owes the sweep, because the trade is real in both
# directions: a bigger outline buys honesty about what was dropped and costs
# the evidence that would have answered the question.
#
# Derived here rather than imported: builder.py imports THIS module, so
# importing PROMPT_BUDGET back would be a cycle.
OUTLINE_BUDGET = 4000

Row = tuple[str, Chunk]


def build_context(
    chunks: tuple[Chunk, ...],
    selected: tuple[Chunk, ...],
    *,
    totals: dict[str, int] | None = None,
) -> str:
    ids = assign_ids(chunks)
    kept = set(selected)

    unknown = kept - set(ids.values())
    if unknown:
        raise ValueError(f"{len(unknown)} selected chunks are not in chunks")

    parts = []
    for side in SIDES:
        on_side = [(name, chunk) for name, chunk in ids.items() if chunk.side == side]
        if not on_side:
            continue
        # On the SEARCH path these chunks are all we retrieved, not all there
        # is - and every one of them is "kept", so without this the outline
        # would render "every part below is included" over 20 rows of an 8,333
        # part corpus. That is the exact lie the outline exists to prevent: a
        # gap in OUR retrieval reported as a defect in the USER's code.
        total = (totals or {}).get(side)
        partial = total is not None and total > len(on_side)
        heading = f"SIDE {side}"
        if partial:
            heading += (
                f" — {len(on_side)} of {total} parts were retrieved for this "
                f"question. The rest were NOT searched, and you have not read them."
            )
        parts.append(
            f"{heading}\n\n{_outline(on_side, kept, partial=partial)}"
            f"\n\n{_text(on_side, kept)}"
        )

    return "\n\n\n".join(parts)


def _outline(
    on_side: list[tuple[str, Chunk]],
    kept: set[Chunk],
    *,
    partial: bool = False,
) -> str:
    if not partial and all(chunk in kept for _, chunk in on_side):
        return _all_included(on_side)

    rendered = ""
    for render in (_per_chunk, _per_file_with_labels, _per_file):
        rendered = render(on_side, kept)
        if estimate_tokens(rendered) <= OUTLINE_BUDGET:
            break

    return rendered


def _per_chunk(on_side: list[Row], kept: set[Chunk]) -> str:
    rows = "\n".join(
        f"{name}  {INCLUDED if chunk in kept else DROPPED}  {chunk.header}"
        for name, chunk in on_side
    )

    return f"ALL PARTS, IN ORDER\n{rows}"


def _per_file_with_labels(on_side: list[Row], kept: set[Chunk]) -> str:
    return _per_file(on_side, kept, labels=True)


def _per_file(on_side: list[Row], kept: set[Chunk], *, labels: bool = False) -> str:
    rows: list[str] = []
    for source, group in _by_file(on_side):
        rows.append(f"{_file_row(source, group)}  ·  {_how_much(group, kept)}")
        if labels and (defines := _labels(group)):
            rows.append(f"          defines: {', '.join(defines)}")

    return "FILES\n" + "\n".join(rows)


def _all_included(on_side: list[Row]) -> str:
    rows = "\n".join(_file_row(source, group) for source, group in _by_file(on_side))
    return f"FILES - every part below is included\n{rows}"


def _by_file(on_side: list[Row]) -> list[tuple[str, list[Row]]]:
    """Group CONSECUTIVE rows by file, never sort-and-group.

    That choice is what makes the printed id span honest. `B-40..B-70` is only
    true if a file's chunks sit together, which they do today because
    chunk_source walks files in sorted order - but nothing enforces it. Group
    by consecutive runs and a file that is ever split renders as two rows with
    two correct spans, instead of one row whose span silently swallows another
    file's chunks. A wrong span is a citation pointing at the wrong file with
    full confidence, which is exactly what this module exists to prevent.
    """
    groups: list[tuple[str, list[Row]]] = []
    for row in on_side:
        if groups and groups[-1][0] == row[1].source:
            groups[-1][1].append(row)
        else:
            groups.append((row[1].source, [row]))

    return groups


def _file_row(source: str, group: list[Row]) -> str:
    first, last = group[0][0], group[-1][0]
    span = first if first == last else f"{first}..{last}"
    lines = f"lines {group[0][1].start_line}-{group[-1][1].end_line}"

    return f"{source}  {span}  {len(group)} parts, {lines}"


def _how_much(group: list[Row], kept: set[Chunk]) -> str:
    sent = sum(1 for _, chunk in group if chunk in kept)

    return f"{sent} {INCLUDED}" if sent else f"none {INCLUDED}"


def _labels(group: list[Row]) -> list[str]:
    found: dict[str, None] = {}
    for _, chunk in group:
        parts = [piece.strip() for piece in chunk.header.strip("[]").split("·")]
        if len(parts) > 2:
            found[parts[1]] = None

    return list(found)


def _text(on_side: list[tuple[str, Chunk]], kept: set[Chunk]) -> str:
    blocks = "\n\n".join(
        f"{name}  {chunk.header}\n{chunk.text}"
        for name, chunk in on_side
        if chunk in kept
    )
    return f"TEXT\n{blocks or NOTHING_SENT}"
