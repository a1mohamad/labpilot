from __future__ import annotations

from dataclasses import replace

from labpilot.ingest._recursive import split_recursive
from labpilot.ingest.contracts import Piece
from labpilot.ingest.defaults import MAX_CHARS, MIN_CHARS


def reserve(source: str, label: str, digits: int) -> int:
    """Characters the header could take for this piece, at its very worst.

    Deliberately pessimistic: it always allows for a `part i/n` suffix and for
    the widest line numbers the file can produce, so the budget can be fixed
    BEFORE the split decides either of them. Over-reserving costs a few
    characters of chunk; under-reserving is the bug this exists to remove.
    """
    widest = "9" * digits
    parts = [source, label, "part 999/999", f"lines {widest}-{widest}"]
    # +1 for the newline embed_text puts between the header and the text.
    return len("[" + " · ".join(part for part in parts if part) + "]") + 1


def _budget(source: str, label: str, digits: int) -> int:
    return MAX_CHARS - reserve(source, label, digits)


def enforce_cap(pieces: list[Piece], source: str, digits: int) -> list[Piece]:
    kept: list[Piece] = []
    for piece in pieces:
        budget = _budget(source, piece.label, digits)
        if len(piece.text) <= budget:
            kept.append(piece)
            continue
        parts = split_recursive(
            piece.text, start_line=piece.start_line, max_chars=budget
        )
        total = len(parts)
        for position, part in enumerate(parts, start=1):
            label = _part_label(piece.label, position, total)
            kept.append(replace(part, label=label))
    return kept


def _part_label(label: str, position: int, total: int) -> str:
    part = f"part {position}/{total}"
    return f"{label} · {part}" if label else part


def merge_small(
    pieces: list[Piece], lines: list[str], source: str, digits: int
) -> list[Piece]:
    merged = list(pieces)
    index = 0
    while index < len(merged):
        if len(merged[index].text) >= MIN_CHARS:
            index += 1
            continue
        target = _merge_target(merged, index, lines, source, digits)
        if target is None:
            index += 1
            continue
        low, high = sorted((index, target))
        merged[low : high + 1] = [_join(merged[low], merged[high], lines)]
        index = low
    return merged


def _merge_target(
    pieces: list[Piece], index: int, lines: list[str], source: str, digits: int
) -> int | None:
    candidates = [
        neighbour
        for neighbour in (index + 1, index - 1)
        if 0 <= neighbour < len(pieces)
        and _fits(pieces[index], pieces[neighbour], lines, source, digits)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda n: _shared_label(pieces[index], pieces[n]))


def _fits(one: Piece, other: Piece, lines: list[str], source: str, digits: int) -> bool:
    # A merge must not create the very chunk the cap exists to prevent, so it
    # is measured against the same header-aware budget as a split.
    kept = _join(one, other, lines).label
    return len(_span_text(one, other, lines)) <= _budget(source, kept, digits)


def _span_text(one: Piece, other: Piece, lines: list[str]) -> str:
    start = min(one.start_line, other.start_line)
    end = max(one.end_line, other.end_line)
    return "\n".join(lines[start - 1 : end])


def _shared_label(one: Piece, other: Piece) -> int:
    left = one.label.split(" · ")
    right = other.label.split(" · ")
    shared = 0
    for first, second in zip(left, right, strict=False):
        if first != second:
            break
        shared += 1
    return shared


def _join(first: Piece, second: Piece, lines: list[str]) -> Piece:
    return Piece(
        text=_span_text(first, second, lines),
        start_line=min(first.start_line, second.start_line),
        end_line=max(first.end_line, second.end_line),
        label=first.label if len(first.text) >= len(second.text) else second.label,
    )
