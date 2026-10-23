import pytest

from labpilot.agent import (
    CHECK_TOOL_NAME,
    KINDS,
    UNCHECKED,
    VERDICTS,
    CheckError,
    Claim,
    Finding,
    check_schema,
    read_finding,
)

CLAIM = Claim("the time step is 0.01 s", "[paper.md · 4 Setup]", "time step is 0.01 s")
SOURCES = ["[solver.py · lines 1-5]", "[solver.py · lines 6-9]"]
TEXTS = [f"{SOURCES[0]}\nmesh = 200", f"{SOURCES[1]}\ndt = 0.05"]


def verdict(**fields):
    base = {
        "verdict": "mismatch",
        "kind": "choice",
        "part": 1,
        "quote": "dt = 0.05",
        "note": "B uses a bigger step",
    }
    return {**base, **fields}


def without(arguments, key):
    return {name: value for name, value in arguments.items() if name != key}


def test_the_schema_needs_only_a_verdict_and_a_note_and_lists_what_is_allowed():
    schema = check_schema()

    assert schema["required"] == ["verdict", "note"]
    assert schema["properties"]["verdict"]["enum"] == list(VERDICTS)
    assert schema["properties"]["kind"]["enum"] == list(KINDS)
    assert CHECK_TOOL_NAME == "give_verdict"


def test_the_model_cannot_choose_unchecked_that_is_for_a_claim_no_tier_could_check():
    assert UNCHECKED not in VERDICTS


def test_a_mismatch_gets_the_place_of_the_part_the_model_named():
    found = read_finding(verdict(), CLAIM, SOURCES, TEXTS)

    assert found == Finding(
        CLAIM,
        "mismatch",
        "choice",
        SOURCES[1],
        "dt = 0.05",
        "B uses a bigger step",
    )


def test_a_match_has_no_kind_even_when_the_model_gave_one():
    found = read_finding(
        verdict(verdict="match", quote="DT = 0.05"), CLAIM, SOURCES, TEXTS
    )

    assert (found.verdict, found.kind, found.source) == ("match", "", SOURCES[1])


def test_an_absent_needs_no_part_and_no_quote_and_keeps_none():
    arguments = {"verdict": "absent", "note": "no step in these parts"}

    found = read_finding(arguments, CLAIM, SOURCES, TEXTS)

    assert found == Finding(CLAIM, "absent", "", "", "", "no step in these parts")


def test_an_absent_ignores_a_part_and_a_quote_the_model_gave_anyway():
    arguments = verdict(verdict="absent", quote="it was never said")

    found = read_finding(arguments, CLAIM, SOURCES, TEXTS)

    assert (found.source, found.quote, found.kind) == ("", "", "")


def test_the_note_and_the_quote_lose_the_spaces_around_them():
    arguments = verdict(quote="  dt = 0.05 ", note="  a bigger step  ")

    found = read_finding(arguments, CLAIM, SOURCES, TEXTS)

    assert (found.quote, found.note) == ("dt = 0.05", "a bigger step")


@pytest.mark.parametrize(
    "arguments",
    [
        without(verdict(), "verdict"),
        verdict(verdict="maybe"),
        verdict(verdict=None),
        without(verdict(), "note"),
        verdict(note=3),
        without(verdict(), "part"),
        verdict(part="1"),
        verdict(part=1.0),
        verdict(part=True),
        verdict(part=-1),
        verdict(part=2),
        without(verdict(), "quote"),
        verdict(quote=3),
        verdict(quote=""),
        verdict(quote="dt = 0.5"),
        without(verdict(), "kind"),
        verdict(kind="bug"),
        verdict(verdict="match", part=5),
        verdict(verdict="match", quote="it was never said"),
    ],
)
def test_an_answer_that_is_not_a_good_verdict_is_refused(arguments):
    with pytest.raises(CheckError):
        read_finding(arguments, CLAIM, SOURCES, TEXTS)


def test_the_quote_is_looked_up_in_the_part_the_model_named_and_in_no_other():
    # "mesh = 200" is really in part 0, and the model named part 1.
    with pytest.raises(CheckError, match="part 1"):
        read_finding(verdict(quote="mesh = 200"), CLAIM, SOURCES, TEXTS)


def test_parts_and_sources_that_do_not_match_are_a_bug_of_the_caller():
    with pytest.raises(ValueError):
        read_finding(verdict(), CLAIM, SOURCES, TEXTS[:1])
