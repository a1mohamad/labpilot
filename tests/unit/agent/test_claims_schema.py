import logging

import pytest

from labpilot.agent import (
    CLAIMS_TOOL_NAME,
    MAX_CLAIMS,
    MAX_CLAIMS_PER_ANSWER,
    METHOD,
    RESULT,
    Claim,
    ClaimsError,
    claims_schema,
    join_claims,
    read_claims,
)

SOURCES = ["[paper.md · 3 Method · lines 1-9]", "[paper.md · 4 Setup · lines 10-19]"]
TEXTS = ["The mesh has 200 cells.", "The time step is 0.01 s."]


def claim(text, part, quote):
    return {"text": text, "part": part, "quote": quote}


def test_the_schema_asks_for_a_text_a_part_number_and_a_quote_for_every_claim():
    item = claims_schema()["properties"]["claims"]["items"]

    assert item["required"] == ["text", "part", "quote"]
    assert item["properties"]["part"] == {"type": "integer"}
    assert item["properties"]["quote"] == {"type": "string"}
    assert CLAIMS_TOOL_NAME == "list_claims"


def test_the_place_of_a_claim_comes_from_its_part_number_and_not_from_the_model():
    arguments = {
        "claims": [
            claim("the time step is 0.01 s", 1, "time step is 0.01 s"),
            claim("the mesh has 200 cells", 0, "mesh has 200 cells"),
        ]
    }

    assert read_claims(arguments, SOURCES, TEXTS) == (
        Claim("the time step is 0.01 s", SOURCES[1], "time step is 0.01 s"),
        Claim("the mesh has 200 cells", SOURCES[0], "mesh has 200 cells"),
    )


def test_the_text_and_the_quote_of_a_claim_lose_the_spaces_around_them():
    arguments = {"claims": [claim("  a fact  ", 0, "  mesh has 200 cells ")]}

    found = read_claims(arguments, SOURCES, TEXTS)[0]

    assert (found.text, found.quote) == ("a fact", "mesh has 200 cells")


def test_an_empty_list_is_a_valid_answer():
    assert read_claims({"claims": []}, SOURCES, TEXTS) == ()


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"claims": "a fact"},
        {"claims": ["a fact"]},
        {"claims": [{"part": 0, "quote": "mesh"}]},
        {"claims": [{"text": "a fact", "quote": "mesh"}]},
        {"claims": [{"text": "a fact", "part": 0}]},
        {"claims": [claim(3, 0, "mesh")]},
        {"claims": [claim("a fact", "0", "mesh")]},
        {"claims": [claim("a fact", 0.0, "mesh")]},
        {"claims": [claim("a fact", True, "mesh")]},
        {"claims": [claim("a fact", 0, 3)]},
        {"claims": [claim("   ", 0, "mesh")]},
        {"claims": [claim("a fact", -1, "mesh")]},
        {"claims": [claim("a fact", 2, "mesh")]},
    ],
)
def test_an_answer_that_is_not_a_list_of_good_claims_is_refused(arguments):
    with pytest.raises(ClaimsError):
        read_claims(arguments, SOURCES, TEXTS)


def test_a_runaway_list_is_refused():
    runaway = {"claims": [claim(f"fact {n}", 0, "mesh") for n in range(81)]}
    assert MAX_CLAIMS_PER_ANSWER < 81

    with pytest.raises(ClaimsError, match="limit"):
        read_claims(runaway, SOURCES, TEXTS)


def test_a_list_as_long_as_the_limit_is_accepted():
    many = range(MAX_CLAIMS_PER_ANSWER)
    arguments = {"claims": [claim(f"fact {n}", 0, "mesh") for n in many]}

    assert len(read_claims(arguments, SOURCES, TEXTS)) == MAX_CLAIMS_PER_ANSWER


def test_the_schema_offers_the_two_kinds_and_does_not_require_one():
    item = claims_schema()["properties"]["claims"]["items"]

    assert item["properties"]["kind"]["enum"] == [METHOD, RESULT]
    assert "kind" not in item["required"]


@pytest.mark.parametrize(
    ("given", "kind"),
    [("result", RESULT), ("method", METHOD), (None, METHOD), ("a value", METHOD)],
)
def test_a_claim_is_a_method_claim_unless_the_model_says_result(given, kind):
    item = claim("the mesh has 200 cells", 0, "mesh has 200 cells")
    if given is not None:
        item["kind"] = given

    assert read_claims({"claims": [item]}, SOURCES, TEXTS)[0].kind == kind


def made(text, kind=METHOD):
    return Claim(text, "[paper.md]", text, kind)


def test_the_groups_are_joined_in_turn_so_no_group_is_starved():
    first = (made("a1"), made("a2"), made("a3"))
    second = (made("b1"),)

    joined = join_claims([first, second])

    assert [c.text for c in joined] == ["a1", "b1", "a2", "a3"]


def test_a_claim_said_twice_is_kept_once():
    joined = join_claims(
        [(made("The mesh  has 200 cells"),), (made("the mesh has 200 cells"),)]
    )

    assert [c.text for c in joined] == ["The mesh  has 200 cells"]


def test_only_method_claims_count_toward_the_limit():
    methods = tuple(made(f"m{n}") for n in range(MAX_CLAIMS + 5))
    results = tuple(made(f"r{n}", RESULT) for n in range(3))

    joined = join_claims([methods, results])

    assert sum(c.kind == METHOD for c in joined) == MAX_CLAIMS
    assert sum(c.kind == RESULT for c in joined) == 3


def test_no_groups_join_to_nothing():
    assert join_claims([]) == ()


def test_parts_and_sources_that_do_not_match_are_a_bug_of_the_caller():
    with pytest.raises(ValueError):
        read_claims({"claims": []}, SOURCES, TEXTS[:1])


def test_a_claim_whose_quote_is_not_in_its_part_is_dropped_and_the_others_stay(caplog):
    arguments = {
        "claims": [
            claim("the mesh has 400 cells", 0, "mesh has 400 cells"),
            claim("the time step is 0.01 s", 1, "time step is 0.01 s"),
        ]
    }

    with caplog.at_level(logging.WARNING):
        found = read_claims(arguments, SOURCES, TEXTS)

    assert [item.text for item in found] == ["the time step is 0.01 s"]
    assert "1 of 2 claims dropped" in caplog.text


def test_the_quote_is_looked_up_in_the_part_the_model_named_and_in_no_other():
    arguments = {
        "claims": [
            claim("the time step is 0.01 s", 0, "time step is 0.01 s"),
            claim("the mesh has 200 cells", 0, "mesh has 200 cells"),
        ]
    }

    found = read_claims(arguments, SOURCES, TEXTS)

    assert [item.text for item in found] == ["the mesh has 200 cells"]


def test_when_no_quote_is_in_its_part_the_whole_answer_is_refused():
    arguments = {"claims": [claim("a made up fact", 0, "it was never said")]}

    with pytest.raises(ClaimsError, match="quote"):
        read_claims(arguments, SOURCES, TEXTS)


def test_the_cap_of_method_claims_is_forty_eight_whatever_the_constant_says():
    methods = tuple(made(f"m{n}") for n in range(60))

    joined = join_claims([methods])

    assert MAX_CLAIMS == 48
    assert len(joined) == 48
