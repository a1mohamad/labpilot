from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Protocol

from labpilot.tokens import estimate_tokens

SIDES = ("A", "B")

# How much of the planner's prompt the map of BOTH artifacts may spend.
#
# Its OWN budget, not OUTLINE_BUDGET: the outline competes with retrieved
# evidence in the report, the map competes with nothing but the question and
# the planner's instructions (D10, CLAUDE.md Step 2 section 5b).
#
# 12,000 is what is LEFT of Gemma's 16,000 input cap - the largest free quota
# here, and the line that binds - once the rest of the planner call is paid:
#
#   16,000 / 1.1 (the _check_fits margin)              ~14,500
#   - instructions ~2,000, question ~500, schema ~300   ~12,000
#
# The cap counts INPUT only (measured: InputTokensPerModelPerMinute), so the
# planner's answer needs no room here. The earlier 8,000 kept half the cap for
# "the rest", and the rest is nowhere near half.
#
# IT IS A CEILING, NOT A MEASURED BEST. M5 owes the sweep - 1k, 4k, 8k, 12k and
# a DYNAMIC budget (the tier's input limit / 1.1, minus what the rest of the
# prompt really costs, as the report path does with reserve()). aider's 1k is a
# DEFAULT, not a measurement, and aider doubles it when no files are open - the
# case our planner is always in. The caller applies the per-tier cap:
# min(PLANNER_BUDGET, what this tier can take).
PLANNER_BUDGET = 12_000

NOT_LISTED = "(contents not listed)"
RANKED_NOTE = (
    "Ranked by closeness to the question: files lower down show their name only."
)
FOLDED_NOTE = "Too many files to list: the rest are counted by folder."

# A header is "[source · label · label · part 2/5 · lines 10-40]". The last two
# pieces say WHERE a chunk is, not WHAT it is, so they are never names.
_POSITION = re.compile(r"^(part \d+/\d+|lines \d+-\d+)$")


class MapPart(Protocol):
    """What the map needs from a chunk. StoredHeader has exactly this shape.

    A Protocol and not an import: prompts/ is core and may not see store/, so
    the entry layer hands over whatever it read and this module never names it.
    """

    header: str
    source: str
    start_line: int
    end_line: int


@dataclass
class _Unit:
    name: str
    start: int
    end: int
    members: dict[str, None] = field(default_factory=dict)


@dataclass
class _File:
    source: str
    order: int
    parts: int
    start: int
    end: int
    units: dict[str, _Unit]

    def summary(self) -> str:
        lines = f"lines {self.start}-{self.end}"
        return f"{self.source}   {_count(self.parts, 'part')}, {lines}"

    def brief(self) -> str:
        if not self.units:
            return self.summary()
        return f"{self.summary()}   {NOT_LISTED}"

    def detail(self) -> str:
        rows = [self.summary()]
        for unit in self.units.values():
            row = f"  {unit.name}   lines {unit.start}-{unit.end}"
            if unit.members:
                row += f"   {', '.join(unit.members)}"
            rows.append(row)
        return "\n".join(rows)


@dataclass
class _Rendered:
    text: str
    tokens: int
    complete: bool


def build_map(
    parts: Mapping[str, Sequence[MapPart]],
    *,
    scores: Mapping[str, Mapping[str, float]] | None = None,
    budget: int = PLANNER_BUDGET,
) -> str:
    """A map of what each artifact contains, for a planner that has read none of it.

    Built from chunk HEADERS alone, so it costs one light read per artifact and
    no chunk text. `scores` maps side -> file -> closeness to the question; it
    is used only when the map does not fit, and it BIASES the map, never
    FILTERS it - every file keeps at least a line, because hiding the file the
    question did not mention is the one failure a map exists to prevent.
    """
    if budget < 1:
        raise ValueError(f"budget must be positive, got {budget}")

    sides = [side for side in SIDES if parts.get(side)]
    if not sides:
        return ""

    files = {side: _files(parts[side]) for side in sides}
    ranks = {side: (scores or {}).get(side) for side in sides}

    # EQUAL SHARE, and the leftover flows over - the selector's rule, for the
    # same reason: fixed halves waste a small side's room, and "A before B"
    # would let a large reference starve B out of the map entirely.
    share = budget // len(sides)
    rendered = {side: _side(side, files[side], ranks[side], share) for side in sides}
    spare = sum(share - r.tokens for r in rendered.values() if r.complete)
    for side in sides:
        if not rendered[side].complete and spare > 0:
            rendered[side] = _side(side, files[side], ranks[side], share + spare)

    return "\n\n\n".join(rendered[side].text for side in sides)


def _files(parts: Sequence[MapPart]) -> list[_File]:
    """Group CONSECUTIVE parts by file, as context._by_file does, and why.

    A file split across two runs becomes two rows with two correct line spans,
    instead of one row whose span silently swallows another file.
    """
    files: list[_File] = []
    for part in parts:
        if not files or files[-1].source != part.source:
            files.append(
                _File(
                    source=part.source,
                    order=len(files),
                    parts=0,
                    start=part.start_line,
                    end=part.end_line,
                    units={},
                )
            )
        current = files[-1]
        current.parts += 1
        current.start = min(current.start, part.start_line)
        current.end = max(current.end, part.end_line)

        names = _names(part)
        if not names:
            continue
        unit = current.units.setdefault(
            names[0], _Unit(names[0], part.start_line, part.end_line)
        )
        unit.start = min(unit.start, part.start_line)
        unit.end = max(unit.end, part.end_line)
        if len(names) > 1:
            unit.members[names[1]] = None

    return files


def _names(part: MapPart) -> list[str]:
    pieces = [piece.strip() for piece in part.header.strip().strip("[]").split("·")]
    if pieces and pieces[0] == part.source:
        pieces = pieces[1:]
    return [piece for piece in pieces if piece and not _POSITION.match(piece)]


def _side(
    side: str,
    files: list[_File],
    scores: Mapping[str, float] | None,
    budget: int,
) -> _Rendered:
    parts = _count(sum(f.parts for f in files), "part")
    heading = f"SIDE {side} — {_count(len(files), 'file')}, {parts}"

    # 1. EVERYTHING FITS - no ranking at all. Most repositories land here, and
    #    ranking then would be a cost with no benefit.
    full = _join(heading, "FILES", [f.detail() for f in files])
    if estimate_tokens(full) <= budget:
        return _Rendered(full, estimate_tokens(full), complete=True)

    # Closest to the question first; the artifact's own order breaks ties and
    # stands in when there are no scores, so the map is always deterministic.
    ranked = sorted(
        files,
        key=lambda f: (-(scores or {}).get(f.source, float("-inf")), f.order),
    )

    # 2. ONE LINE PER FILE, then give contents back in rank order while they
    #    fit. A file that does not fit is skipped, not the end of the loop - a
    #    smaller one further down may still fit.
    rows = {f.order: f.brief() for f in files}
    text = _join(heading, RANKED_NOTE, [rows[f.order] for f in files])
    if estimate_tokens(text) <= budget:
        for file in ranked:
            rows[file.order] = file.detail()
            trial = _join(heading, RANKED_NOTE, [rows[f.order] for f in files])
            if estimate_tokens(trial) <= budget:
                text = trial
            else:
                rows[file.order] = file.brief()
        return _Rendered(text, estimate_tokens(text), complete=False)

    # 3. EVEN ONE LINE PER FILE IS TOO MUCH - count the rest by folder, and
    #    name the closest files while room remains. This is the floor: every
    #    file is still accounted for, named or counted, even if the floor
    #    itself runs over. Below it, the only way to save more is to hide
    #    files, and that is the failure this map exists to prevent.
    named: set[int] = set()
    text = _folded(heading, files, named)
    for file in ranked:
        trial = _folded(heading, files, named | {file.order})
        if estimate_tokens(trial) > budget:
            break
        named.add(file.order)
        text = trial
    return _Rendered(text, estimate_tokens(text), complete=False)


def _folded(heading: str, files: list[_File], named: set[int]) -> str:
    rows = [f.brief() for f in files if f.order in named]
    folders: dict[str, list[_File]] = {}
    for file in files:
        if file.order not in named:
            folders.setdefault(_folder(file.source), []).append(file)
    word = "more file" if named else "file"
    for folder, members in folders.items():
        parts = _count(sum(f.parts for f in members), "part")
        rows.append(f"{folder}   {_count(len(members), word)}, {parts}")
    return _join(heading, FOLDED_NOTE, rows)


def _folder(source: str) -> str:
    parent = PurePosixPath(source.replace("\\", "/")).parent
    return "(top level)" if str(parent) == "." else f"{parent}/"


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _join(heading: str, note: str, rows: list[str]) -> str:
    return "\n".join([heading, note, *rows])
