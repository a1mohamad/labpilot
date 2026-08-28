from __future__ import annotations

from labpilot.ingest.contracts import Piece

Mark = tuple[int, str]


def to_pieces(lines: list[str], marks: list[Mark]) -> list[Piece]:
    return _pieces(lines, _sections(lines, marks))


def _sections(lines: list[str], marks: list[Mark]) -> list[tuple[int, int, str]]:
    if not marks:
        return [(0, len(lines), "")]

    sections = []
    if marks[0][0] > 0:
        sections.append((0, marks[0][0], ""))

    for position, (index, label) in enumerate(marks):
        end = marks[position + 1][0] if position + 1 < len(marks) else len(lines)
        sections.append((index, end, label))

    return sections


def _pieces(lines: list[str], sections: list[tuple[int, int, str]]) -> list[Piece]:
    pieces = []
    for start, end, label in sections:
        while start < end and not lines[start].strip():
            start += 1
        while end > start and not lines[end - 1].strip():
            end -= 1
        if start >= end:
            continue
        pieces.append(
            Piece(
                text="\n".join(lines[start:end]),
                start_line=start + 1,
                end_line=end,
                label=label,
            )
        )
    return pieces
