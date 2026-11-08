import logging

import pytest

from labpilot.agent import (
    BUG_KINDS,
    MAX_BUGS_PER_ANSWER,
    Bug,
    BugsError,
    bugs_schema,
    merge_bugs,
    read_bugs,
)
from labpilot.agent._quote import place_quote
from labpilot.ingest import Chunk

SOURCES = ["[train.py · def step · lines 1-9]", "[train.py · def eval · lines 10-19]"]


TEXTS = ["bias2 = 1 - beta1**step", "threshold = best_on(val)"]


def defect(text, part, quote, kind="logic", severity="high"):
    return {
        "kind": kind,
        "part": part,
        "quote": quote,
        "text": text,
        "severity": severity,
    }


def chunk(index):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
    )


RUNAWAY = [defect(f"x {n}", 0, "beta1") for n in range(MAX_BUGS_PER_ANSWER + 1)]


def test_the_kinds_are_code_logic_method_numbers_and_concept():
    item = bugs_schema()["properties"]["defects"]["items"]

    assert BUG_KINDS == ("code", "logic", "method", "numbers", "concept")
    assert item["properties"]["kind"]["enum"] == list(BUG_KINDS)
    assert item["required"] == ["kind", "part", "quote", "text"]


def test_a_suspect_gets_its_place_from_its_part_number():
    arguments = {"defects": [defect("tuned on val", 1, "best_on(val)", "method")]}

    (got,) = read_bugs(arguments, SOURCES, TEXTS)

    assert got == Bug("method", "tuned on val", SOURCES[1], "best_on(val)", "high")


@pytest.mark.parametrize("kind,severity", [("style", "huge"), (None, None)])
def test_an_unknown_kind_or_severity_falls_back_to_code_and_high(kind, severity):
    arguments = {"defects": [defect("x", 0, "beta1**step", kind, severity)]}

    got = read_bugs(arguments, SOURCES, TEXTS)[0]

    assert (got.kind, got.severity) == ("code", "high")


def test_a_suspect_whose_quote_is_not_in_its_part_is_dropped(caplog):
    arguments = {
        "defects": [defect("made up", 0, "never written"), defect("real", 0, "beta1")]
    }

    with caplog.at_level(logging.WARNING):
        got = read_bugs(arguments, SOURCES, TEXTS)

    assert [g.text for g in got] == ["real"]
    assert "1 of 2 suspects dropped" in caplog.text


def test_the_part_that_shows_it_is_kept_when_the_parts_are_given():
    parts = [chunk(0), chunk(1)]
    arguments = {"defects": [defect("tuned", 1, "best_on(val)")]}

    assert read_bugs(arguments, SOURCES, TEXTS, parts)[0].evidence is parts[1]


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"defects": "x"},
        {"defects": [defect("x", 5, "beta1")]},
        {"defects": [defect("  ", 0, "beta1")]},
        {"defects": [defect("x", 0, "nowhere")]},
        {"defects": [{**defect("x", 0, "beta1"), "part": True}]},
        {"defects": RUNAWAY},
    ],
)
def test_an_answer_that_is_not_a_good_list_is_refused(arguments):
    with pytest.raises(BugsError):
        read_bugs(arguments, SOURCES, TEXTS)


def test_two_questions_that_point_at_one_line_give_one_suspect():
    first = Bug("logic", "wrong beta", "[a]", "bias2 = 1 - beta1**step")
    again = Bug("concept", "beta1 again", "[a]", "bias2  =  1 - beta1**step")
    elsewhere = Bug("logic", "wrong beta", "[b]", "bias2 = 1 - beta1**step")

    assert merge_bugs([first, again, elsewhere]) == (first, elsewhere)


def test_a_quote_named_in_the_wrong_part_is_placed_where_it_is():
    got = read_bugs({"defects": [defect("leak", 0, "best_on(val)")]}, SOURCES, TEXTS)

    assert [(g.source, g.quote) for g in got] == [(SOURCES[1], "best_on(val)")]


def test_two_lines_joined_with_dots_are_placed_by_the_first_one():
    texts = ["key = make(10)\nlog(key)", "other"]

    assert place_quote(1, "key = make(10) ... log(key)", texts) == (
        0,
        "key = make(10)",
    )


def test_a_quote_that_is_in_no_part_is_not_placed():
    assert place_quote(0, "never written ... nowhere at all", TEXTS) is None


def test_a_short_piece_of_a_quote_is_not_used_to_place_it():
    # "1 - b" alone would match far too much.
    assert place_quote(0, "1 - b ... something else entirely", ["1 - b", "x"]) is None


def test_one_bad_suspect_is_dropped_and_the_others_are_kept():
    arguments = {
        "defects": [
            {"kind": "logic", "quote": "beta1", "text": "no part"},
            defect("tuned on val", 1, "best_on(val)", "method"),
        ]
    }

    assert [g.text for g in read_bugs(arguments, SOURCES, TEXTS)] == ["tuned on val"]
