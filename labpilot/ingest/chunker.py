from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from labpilot.ingest._docx import load_docx
from labpilot.ingest._markdown import split_markdown
from labpilot.ingest._notebook import load_notebook, split_notebook
from labpilot.ingest._pdf import load_pdf, split_pdf
from labpilot.ingest._plain import load_text
from labpilot.ingest._python import split_python
from labpilot.ingest._recursive import split_recursive
from labpilot.ingest.contracts import Chunk, Piece, Side
from labpilot.ingest.defaults import MAX_CHARS, MAX_MEAN_LINE_CHARS, MIN_CHARS
from labpilot.ingest.errors import LooksGenerated

# A loader turns the bytes of a file into the text we mean to read; a splitter
# turns that text into boundaries. Plain text needs no entry: load_text is the
# default, so only formats that are not already text appear here.
LOADERS: dict[str, Callable[[bytes], str]] = {
    ".ipynb": load_notebook,
    ".pdf": load_pdf,
    ".docx": load_docx,
}

SPLITTERS: dict[str, Callable[[str], list[Piece]]] = {
    ".md": split_markdown,
    ".markdown": split_markdown,
    ".py": split_python,
    ".ipynb": split_notebook,
    ".pdf": split_pdf,
}


def chunk_bytes(
    raw: bytes, *, source: str, side: Side, artifact_id: str
) -> tuple[Chunk, ...]:
    # Loading happens here, not in chunk_file, because an upload arrives as
    # bytes through the API and would otherwise reach the splitter unloaded.
    suffix = Path(source).suffix.lower()
    text = _load(raw, suffix)
    _refuse_machine_written(text, source)

    # The cap has to be spent on what we SEND, and what we send is
    # chunk.embed_text - the header plus the text. Reserve the header's worst
    # case first, or the cap silently applies to the smaller half.
    lines = text.splitlines()
    digits = len(str(max(len(lines), 1)))

    pieces = _split(text, suffix, max_chars=MAX_CHARS - _reserve(source, "", digits))
    pieces = _merge_small(_enforce_cap(pieces, source, digits), lines, source, digits)
    return tuple(
        _chunk(piece, index, source=source, side=side, artifact_id=artifact_id)
        for index, piece in enumerate(pieces)
    )


def _refuse_machine_written(text: str, source: str) -> None:
    # Minified code is one enormous line, so every chunk reports "lines 1-1"
    # and every citation points at line 1 -- wrong, and it looks right.
    # Measured over 1,386 real source files: the worst mean line is 69, our
    # own loaded PDF and Word text reach 69.3, and jquery.min.js is 43,766.
    lines = text.splitlines()
    if not lines:
        return

    mean = sum(len(line) for line in lines) / len(lines)
    if mean > MAX_MEAN_LINE_CHARS:
        raise LooksGenerated(
            f"{source} averages {mean:.0f} characters per line, over the "
            f"{MAX_MEAN_LINE_CHARS} limit. This is minified or generated: it "
            f"has no lines to cite, so every finding would point at line 1"
        )


def chunk_file(
    path: str | Path, *, side: Side, artifact_id: str, source: str | None = None
) -> tuple[Chunk, ...]:
    path = Path(path)
    return chunk_bytes(
        path.read_bytes(),
        source=source or path.name,
        side=side,
        artifact_id=artifact_id,
    )


def _load(raw: bytes, suffix: str) -> str:
    return LOADERS.get(suffix, load_text)(raw)


def _split(text: str, suffix: str, *, max_chars: int) -> list[Piece]:
    # A format splitter cuts on structure and cannot take a budget; anything
    # it leaves oversized is handled by _enforce_cap, which knows the label.
    splitter = SPLITTERS.get(suffix)
    if splitter is None:
        return split_recursive(text, max_chars=max_chars)
    return splitter(text)


def _reserve(source: str, label: str, digits: int) -> int:
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
    return MAX_CHARS - _reserve(source, label, digits)


def _enforce_cap(pieces: list[Piece], source: str, digits: int) -> list[Piece]:
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


def _merge_small(
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
