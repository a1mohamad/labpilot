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


def test_the_schema_asks_for_a_text_and_a_part_number_for_every_claim():
    item = claims_schema()["properties"]["claims"]["items"]

    assert item["required"] == ["text", "part"]
    assert item["properties"]["part"] == {"type": "integer"}
    assert CLAIMS_TOOL_NAME == "list_claims"


def test_the_place_of_a_claim_comes_from_its_part_number_and_not_from_the_model():
    arguments = {
        "claims": [
            {"text": "the time step is 0.01 s", "part": 1},
            {"text": "the mesh has 200 cells", "part": 0},
        ]
    }

    assert read_claims(arguments, SOURCES) == (
        Claim("the time step is 0.01 s", SOURCES[1]),
        Claim("the mesh has 200 cells", SOURCES[0]),
    )


def test_the_text_of_a_claim_loses_the_spaces_around_it():
    claims = read_claims({"claims": [{"text": "  a fact  ", "part": 0}]}, SOURCES)

    assert claims[0].text == "a fact"


def test_an_empty_list_is_a_valid_answer():
    assert read_claims({"claims": []}, SOURCES) == ()


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"claims": "a fact"},
        {"claims": ["a fact"]},
        {"claims": [{"part": 0}]},
        {"claims": [{"text": "a fact"}]},
        {"claims": [{"text": 3, "part": 0}]},
        {"claims": [{"text": "a fact", "part": "0"}]},
        {"claims": [{"text": "a fact", "part": 0.0}]},
        {"claims": [{"text": "a fact", "part": True}]},
        {"claims": [{"text": "   ", "part": 0}]},
        {"claims": [{"text": "a fact", "part": -1}]},
        {"claims": [{"text": "a fact", "part": 2}]},
    ],
)
def test_an_answer_that_is_not_a_list_of_good_claims_is_refused(arguments):
    with pytest.raises(ClaimsError):
        read_claims(arguments, SOURCES)


def test_a_runaway_list_is_refused():
    runaway = {"claims": [{"text": f"fact {n}", "part": 0} for n in range(21)]}
    assert MAX_CLAIMS < 21

    with pytest.raises(ClaimsError, match="limit"):
        read_claims(runaway, SOURCES)


def test_a_list_as_long_as_the_limit_is_accepted():
    arguments = {
        "claims": [{"text": f"fact {n}", "part": 0} for n in range(MAX_CLAIMS)]
    }

    assert len(read_claims(arguments, SOURCES)) == MAX_CLAIMS
