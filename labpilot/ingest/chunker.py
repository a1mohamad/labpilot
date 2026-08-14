from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from labpilot.ingest._markdown import split_markdown
from labpilot.ingest._python import split_python
from labpilot.ingest._recursive import split_recursive
from labpilot.ingest.contracts import Chunk, Piece, Side
from labpilot.ingest.defaults import MAX_CHARS, MIN_CHARS

SPLITTERS: dict[str, Callable[[str], list[Piece]]] = {
    ".md": split_markdown,
    ".markdown": split_markdown,
    ".py": split_python,
}


def chunk_text(
    text: str, *, source: str, side: Side, artifact_id: str
) -> tuple[Chunk, ...]:
    pieces = _splitter_for(source)(text)
    pieces = _merge_small(_enforce_cap(pieces))
    return tuple(
        _chunk(piece, index, source=source, side=side, artifact_id=artifact_id)
        for index, piece in enumerate(pieces)
    )


def chunk_file(
    path: str | Path, *, side: Side, artifact_id: str, source: str | None = None
) -> tuple[Chunk, ...]:
    path = Path(path)
    return chunk_text(
        path.read_text(encoding="utf-8"),
        source=source or path.name,
        side=side,
        artifact_id=artifact_id,
    )


def _splitter_for(source: str) -> Callable[[str], list[Piece]]:
    return SPLITTERS.get(Path(source).suffix.lower(), split_recursive)


def _enforce_cap(pieces: list[Piece]) -> list[Piece]:
    kept: list[Piece] = []
    for piece in pieces:
        if len(piece.text) <= MAX_CHARS:
            kept.append(piece)
            continue
        parts = split_recursive(piece.text, start_line=piece.start_line)
        total = len(parts)
        for position, part in enumerate(parts, start=1):
            label = _part_label(piece.label, position, total)
            kept.append(replace(part, label=label))
    return kept


def _part_label(label: str, position: int, total: int) -> str:
    part = f"part {position}/{total}"
    return f"{label} . {part}" if label else part


def _merge_small(pieces: list[Piece]) -> list[Piece]:
    merged = list(pieces)
    index = 0
    while index < len(merged):
        if len(merged[index].text) >= MIN_CHARS:
            index += 1
            continue
        target = _merge_target(merged, index)
        if target is None:
            index += 1
            continue
        low, high = sorted((index, target))
        merged[low : high + 1] = [_join(merged[low], merged[high])]
        index = low
    return merged


def _merge_target(pieces: list[Piece], index: int) -> int | None:
    candidates = [
        neighbour
        for neighbour in (index + 1, index - 1)
        if 0 <= neighbour < len(pieces) and _fits(pieces[index], pieces[neighbour])
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda n: _shared_label(pieces[index], pieces[n]))


def _fits(one: Piece, other: Piece) -> bool:
    return len(one.text) + len(other.text) + 1 <= MAX_CHARS


def _shared_label(one: Piece, other: Piece) -> int:
    left = one.label.split(" · ")
    right = other.label.split(" · ")
    shared = 0
    for first, second in zip(left, right, strict=False):
        if first != second:
            break
        shared += 1
    return shared


def _join(first: Piece, second: Piece) -> Piece:
    return Piece(
        text=f"{first.text}\n{second.text}",
        start_line=min(first.start_line, second.start_line),
        end_line=max(first.end_line, second.end_line),
        label=first.label if len(first.text) >= len(second.text) else second.label,
    )


def _chunk(
    piece: Piece, index: int, *, source: str, side: Side, artifact_id: str
) -> Chunk:
    return Chunk(
        text=piece.text,
        source=source,
        start_line=piece.start_line,
        end_line=piece.end_line,
        side=side,
        artifact_id=artifact_id,
        chunk_index=index,
        header=_header(source, piece),
    )


def _header(source: str, piece: Piece) -> str:
    lines = f"lines {piece.start_line}-{piece.end_line}"
    parts = [source, piece.label, lines] if piece.label else [source, lines]
    return f"[{' · '.join(parts)}]"
