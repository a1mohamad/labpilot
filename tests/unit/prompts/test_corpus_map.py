from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from labpilot.prompts import build_map
from labpilot.prompts.corpus_map import NOT_LISTED
from labpilot.tokens import estimate_tokens


@dataclass(frozen=True)
class Part:
    header: str
    source: str
    start_line: int
    end_line: int


def part(source: str, *names: str, start: int, end: int, piece: str = "") -> Part:
    pieces = [source, *names, *([piece] if piece else []), f"lines {start}-{end}"]
    return Part(f"[{' · '.join(pieces)}]", source, start, end)


# Headers exactly as the chunker writes them. `def fit` (a method) and `def main`
# (top level) are each split in two, and the first part of the file is module
# level code with no name at all. The TOP-LEVEL split is the one that matters:
# there "part 1/2" sits where a member name would, and could be listed as one.
TRAIN = [
    part("train.py", start=1, end=120),
    part("train.py", "class Trainer", "def fit", start=920, end=960, piece="part 1/2"),
    part("train.py", "class Trainer", "def fit", start=958, end=1000, piece="part 2/2"),
    part("train.py", "class Trainer", "def evaluate", start=1001, end=1100),
    part("train.py", "def main", start=1400, end=1420, piece="part 1/2"),
    part("train.py", "def main", start=1418, end=1440, piece="part 2/2"),
]
MODEL = [part("model.py", "class Net", "def forward", start=10, end=60)]
PAPER = [part("paper.md", "4.1 Input representation", start=53, end=72)]


def test_a_map_that_fits_lists_every_file_its_units_and_their_members():
    text = build_map({"A": PAPER, "B": TRAIN + MODEL})

    assert "train.py   6 parts, lines 1-1440" in text
    assert "class Trainer   lines 920-1100   def fit, def evaluate" in text
    assert "def main   lines 1400-1440\n" in text
    assert "class Net   lines 10-60   def forward" in text
    assert "4.1 Input representation   lines 53-72" in text
    assert NOT_LISTED not in text
    assert "Ranked" not in text, "a map that fits must not be ranked"


def test_a_function_split_across_parts_is_named_once():
    assert build_map({"B": TRAIN}).count("def fit") == 1


def test_a_position_is_never_mistaken_for_a_name():
    text = build_map({"B": TRAIN})

    assert "part 1/2" not in text
    assert "lines 1-120   " not in text, "module level code has no name to list"


def test_a_side_with_no_parts_is_left_out():
    text = build_map({"A": [], "B": MODEL})

    assert "SIDE A" not in text
    assert "SIDE B" in text


def test_nothing_to_map_is_an_empty_map():
    assert build_map({}) == ""


# ---- when it does NOT fit -------------------------------------------------


def many_files(count: int, folder: str = "pkg") -> list[Part]:
    parts = []
    for n in range(count):
        source = f"{folder}/module_{n:03d}.py"
        for k in range(3):
            parts.append(
                part(
                    source,
                    f"class Thing{n}",
                    f"def step_{k}",
                    start=k * 50 + 1,
                    end=k * 50 + 40,
                )
            )
    return parts


BIG = many_files(40)
SOURCES = sorted({p.source for p in BIG})
# MEASURED on this fixture: one line per file costs ~902 tokens and the full
# map ~1,448. A budget between the two is the only place ranking happens.
TIGHT = 1_000


def listed(text: str) -> set[str]:
    return {s for s in SOURCES if f"{s}   " in text}


def detailed(text: str) -> set[str]:
    return {s for s in SOURCES if f"{s}   3 parts, lines 1-140\n" in text + "\n"}


def test_the_closest_file_to_the_question_keeps_its_contents():
    closest = SOURCES[-1]  # LAST in the artifact, so order alone would not save it
    scores = {"B": {s: (1.0 if s == closest else 0.0) for s in SOURCES}}

    text = build_map({"B": BIG}, scores=scores, budget=TIGHT)

    assert closest in detailed(text)
    assert "Ranked by closeness" in text


def test_a_file_the_question_did_not_mention_is_never_dropped():
    # bias, never filter: hiding what the question did not name is the one
    # failure the map exists to prevent
    scores = {"B": {SOURCES[0]: 1.0}}

    text = build_map({"B": BIG}, scores=scores, budget=TIGHT)

    assert listed(text) == set(SOURCES)
    assert text.count(NOT_LISTED) == len(SOURCES) - len(detailed(text))


def test_without_scores_the_artifacts_own_order_decides():
    text = build_map({"B": BIG}, budget=TIGHT)

    assert SOURCES[0] in detailed(text)
    assert SOURCES[-1] not in detailed(text)


def test_a_file_too_big_to_list_does_not_block_the_smaller_ones_after_it():
    # the closest file has 200 functions and can never fit; stopping at it
    # would leave every smaller file nameless for nothing
    giant = [
        part("pkg/giant.py", "class Giant", f"def method_{k}", start=k, end=k)
        for k in range(200)
    ]
    scores = {"B": {"pkg/giant.py": 1.0}}

    text = build_map({"B": giant + BIG}, scores=scores, budget=TIGHT + 40)

    assert "def method_0" not in text, "premise: the giant must not fit"
    assert detailed(text), "the smaller files after it were never tried"


@pytest.mark.parametrize("budget", [950, TIGHT, 1_300])
def test_a_ranked_map_stays_within_its_budget(budget):
    text = build_map({"B": BIG}, budget=budget)

    assert "Ranked by closeness" in text, "premise: the map must not fit whole"
    assert estimate_tokens(text) <= budget


# ---- when even one line per file does not fit ------------------------------

HUGE = many_files(150, "src/core") + many_files(150, "src/util")
HUGE_SOURCES = [p.source for p in HUGE][::3]


def accounted(text: str) -> int:
    named = sum(1 for s in HUGE_SOURCES if f"{s}   " in text)
    counted = sum(int(n) for n in re.findall(r"/   (\d+) (?:more )?files?,", text))
    return named + counted


def test_too_many_files_are_counted_by_folder_and_none_disappears():
    text = build_map({"B": HUGE}, budget=600)

    assert "counted by folder" in text
    assert accounted(text) == len(HUGE_SOURCES) == 300


def test_the_closest_files_keep_their_names_when_folders_are_counted():
    closest = HUGE_SOURCES[-1]
    text = build_map({"B": HUGE}, scores={"B": {closest: 1.0}}, budget=600)

    assert f"{closest}   " in text


# ---- two sides, one budget ---------------------------------------------------


def test_a_small_side_hands_its_leftover_to_a_large_one():
    budget = 2 * TIGHT
    alone = build_map({"B": BIG}, budget=budget // 2)
    shared = build_map({"A": PAPER, "B": BIG}, budget=budget)

    side_b = shared.split("SIDE B", 1)[1]
    assert len(detailed(side_b)) > len(detailed(alone)), (
        "B got no more room than a fixed half - A's leftover was wasted"
    )


def test_neither_side_is_privileged():
    # the same content in either slot must get the same room: upload order
    # must not decide how much of a comparison the planner can see
    other = [
        Part(
            p.header.replace("pkg/", "lib/"),
            p.source.replace("pkg/", "lib/"),
            p.start_line,
            p.end_line,
        )
        for p in BIG
    ]
    one = build_map({"A": BIG, "B": other}, budget=2_000)
    two = build_map({"A": other, "B": BIG}, budget=2_000)

    a_first = one.split("SIDE B", 1)[0]
    b_second = two.split("SIDE B", 1)[1]
    assert len(detailed(a_first)) == len(detailed(b_second))


def test_a_budget_that_can_hold_nothing_is_a_caller_bug():
    with pytest.raises(ValueError, match="budget"):
        build_map({"B": MODEL}, budget=0)
