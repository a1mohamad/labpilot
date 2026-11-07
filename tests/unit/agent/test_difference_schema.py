import pytest

from labpilot.agent.difference import AUDIT, DIFFERS, MISSING, SCAN, SILENT
from labpilot.agent.difference_schema import (
    JUDGE_VERDICTS,
    RELATIONS,
    audit_schema,
    judge_schema,
    merge_schema,
    read_audit,
    read_judge,
    read_merge,
    read_scan,
    scan_schema,
)
from labpilot.agent.errors import DifferencesError

FACTS = ("the key is 128 bits", "the mask index is i MOD 4", "values are logged")
SOURCES = ("conn.go lines 1-9", "mask.go lines 1-7")
TEXTS = (
    "func read() {\n  if mask {\n    key := p[2:6]\n  }\n}",
    "func maskBytes(b []byte) {\n  b[i] ^= key[pos%3]\n}",
)


def test_the_schemas_ask_for_the_fields_the_readers_need():
    audit = audit_schema()["properties"]["answers"]["items"]
    scan = scan_schema()["properties"]["items"]["items"]
    judge = judge_schema()["properties"]["answers"]["items"]

    assert audit["required"] == ["n", "verdict"]
    assert audit["properties"]["verdict"]["enum"] == [
        "same",
        "differs",
        "missing",
        "n/a",
    ]
    assert scan["required"] == ["part", "quote", "what"]
    assert judge["required"] == ["n", "verdict", "relation"]
    assert judge["properties"]["verdict"]["enum"] == list(JUDGE_VERDICTS)
    assert judge["properties"]["relation"]["enum"] == list(RELATIONS)
    assert merge_schema()["required"] == ["groups"]


def test_the_audit_keeps_every_verdict_and_a_difference_for_differs_and_missing():
    got = read_audit(
        {
            "answers": [
                {
                    "n": 0,
                    "verdict": "missing",
                    "part": 0,
                    "quote": "if mask {",
                    "why": "no check",
                },
                {
                    "n": 1,
                    "verdict": "differs",
                    "part": 1,
                    "quote": "b[i] ^= key[pos%3]",
                    "why": "mod 3",
                },
                {"n": 2, "verdict": "n/a"},
            ]
        },
        FACTS,
        [0, 1, 2],
        SOURCES,
        TEXTS,
    )

    assert got[2] == ("n/a", None)
    verdict, difference = got[1]
    assert verdict == DIFFERS
    assert difference.fact == FACTS[1]
    assert difference.source == SOURCES[1]
    assert difference.found_by == AUDIT
    assert got[0][1].kind == MISSING


def test_a_quote_named_with_the_wrong_part_is_placed_in_the_part_that_holds_it():
    got = read_audit(
        {"answers": [{"n": 1, "verdict": "differs", "part": 0, "quote": "key[pos%3]"}]},
        FACTS,
        [1],
        SOURCES,
        TEXTS,
    )

    assert got[1][1].source == SOURCES[1]


def test_a_flagged_fact_whose_quote_is_nowhere_keeps_its_verdict_with_no_quote():
    got = read_audit(
        {"answers": [{"n": 0, "verdict": "missing", "part": 0, "quote": "invented()"}]},
        FACTS,
        [0],
        SOURCES,
        TEXTS,
    )

    verdict, difference = got[0]
    assert verdict == MISSING
    assert (difference.source, difference.quote) == ("", "")


@pytest.mark.parametrize(
    "answer",
    [
        {"n": 5, "verdict": "same"},  # a fact this call was not asked about
        {"n": True, "verdict": "same"},  # a bool is not a number
        {"n": 0, "verdict": "maybe"},  # not a verdict
        "not a dict",
    ],
)
def test_an_answer_outside_the_rules_is_ignored(answer):
    got = read_audit(
        {"answers": [answer, {"n": 1, "verdict": "same"}]},
        FACTS,
        [0, 1],
        SOURCES,
        TEXTS,
    )

    assert got == {1: ("same", None)}


def test_an_audit_that_answers_nothing_it_was_asked_is_refused():
    with pytest.raises(DifferencesError):
        read_audit(
            {"answers": [{"n": 9, "verdict": "same"}]}, FACTS, [0], SOURCES, TEXTS
        )
    with pytest.raises(DifferencesError):
        read_audit({"answers": "none"}, FACTS, [0], SOURCES, TEXTS)


def test_the_scan_keeps_items_with_a_real_quote_and_drops_invented_ones():
    got = read_scan(
        {
            "items": [
                {
                    "part": 1,
                    "quote": "b[i] ^= key[pos%3]",
                    "what": "masks with mod 3",
                    "why": "wrong bytes",
                },
                {"part": 0, "quote": "nowhere()", "what": "invented"},
                {"part": 0, "quote": "if mask {", "what": ""},
            ]
        },
        SOURCES,
        TEXTS,
    )

    assert len(got) == 1
    assert got[0].kind == SILENT
    assert got[0].found_by == SCAN
    assert got[0].source == SOURCES[1]
    assert got[0].text == "masks with mod 3 wrong bytes"


def test_a_scan_that_returns_no_list_is_refused():
    with pytest.raises(DifferencesError):
        read_scan({"items": None}, SOURCES, TEXTS)


def test_the_judge_reads_numbered_verdicts_and_fixes_an_unknown_relation():
    got = read_judge(
        {
            "answers": [
                {"n": 0, "verdict": "real", "relation": "differs", "why": "mod 3"},
                {"n": 1, "verdict": "false", "relation": "odd", "why": "valid code"},
                {"n": 7, "verdict": "real", "relation": "none"},
            ]
        },
        count=2,
    )

    assert got == {0: ("real", "differs", "mod 3"), 1: ("false", "none", "valid code")}


def test_a_judge_that_answers_no_finding_is_refused():
    with pytest.raises(DifferencesError):
        read_judge(
            {"answers": [{"n": 3, "verdict": "real", "relation": "none"}]}, count=2
        )


def test_the_merge_keeps_groups_of_two_or_more_and_each_finding_once():
    got = read_merge(
        {"groups": [[0, 2], [2, 3], [4], [1, 9, 5]]}, allowed=[0, 1, 2, 3, 4, 5]
    )

    assert got == [[0, 2], [1, 5]]


def test_a_merge_with_no_list_is_refused():
    with pytest.raises(DifferencesError):
        read_merge({"groups": "x"}, allowed=[0, 1])
