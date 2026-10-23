import logging

import pytest

from labpilot.agent import (
    CLAIMS_TOOL_NAME,
    MAX_CLAIMS,
    Claim,
    ClaimsError,
    claims_schema,
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
    runaway = {"claims": [claim(f"fact {n}", 0, "mesh") for n in range(21)]}
    assert MAX_CLAIMS < 21

    with pytest.raises(ClaimsError, match="limit"):
        read_claims(runaway, SOURCES, TEXTS)


def test_a_list_as_long_as_the_limit_is_accepted():
    arguments = {"claims": [claim(f"fact {n}", 0, "mesh") for n in range(MAX_CLAIMS)]}

    assert len(read_claims(arguments, SOURCES, TEXTS)) == MAX_CLAIMS


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
