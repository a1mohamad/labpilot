import pytest

from labpilot.agent import MAX_CLAIMS, Claim, ClaimsError
from labpilot.api import claims
from labpilot.api.errors import UnknownArtifactId
from labpilot.llm import AllFreeTiersExhausted, LLMResult
from labpilot.prompts import CLAIMS_MAX_TOKENS, CLAIMS_WANTED
from labpilot.store import StoredChunk, UnknownArtifact

QUESTION = "Why do the results differ?"
GOOD = {
    "claims": [
        {"text": "the time step is 0.01 s", "part": 1, "quote": "time step is 0.01 s"},
        {"text": "the mesh has 200 cells", "part": 0, "quote": "mesh has 200 cells"},
    ]
}


def chunk(index, text, *, header=None):
    return StoredChunk(
        chunk_index=index,
        text=text,
        header=f"[paper.md · part {index}]" if header is None else header,
        source="paper.md",
        start_line=1,
        end_line=2,
    )


class FakeClient:
    def __init__(self, arguments=None, error=None):
        self.arguments = arguments
        self.error = error
        self.calls = []
        self.hooks = []

    def generate(self, prompt, *, max_tokens, tool=None, problem_with=None):
        self.calls.append((prompt, max_tokens, tool))
        self.hooks.append(problem_with)
        if self.error:
            raise self.error
        return LLMResult(
            text="{}", model="fake-model", tier=1, arguments=self.arguments
        )


def make(monkeypatch, client, *, chunks=(), error=None):
    def fake_read(conn, artifact_id):
        if error:
            raise error
        return tuple(chunks)

    monkeypatch.setattr(claims, "read_chunks", fake_read)
    return claims.make_claims_extractor(object(), client)


TWO_PARTS = [
    chunk(0, "The mesh has 200 cells."),
    chunk(1, "The time step is 0.01 s."),
]


def test_the_claims_get_the_place_of_the_part_the_model_named(monkeypatch):
    extract = make(monkeypatch, FakeClient(GOOD), chunks=TWO_PARTS)

    assert extract(QUESTION, "A-1") == (
        Claim("the time step is 0.01 s", "[paper.md · part 1]", "time step is 0.01 s"),
        Claim("the mesh has 200 cells", "[paper.md · part 0]", "mesh has 200 cells"),
    )


def test_a_part_without_a_header_gets_the_name_of_its_file(monkeypatch):
    parts = [chunk(0, "The mesh has 200 cells.", header="")]
    arguments = {
        "claims": [
            {"text": "the mesh has 200 cells", "part": 0, "quote": "mesh has 200"}
        ]
    }

    result = make(monkeypatch, FakeClient(arguments), chunks=parts)(QUESTION, "A-1")

    assert result[0].source == "paper.md"


def test_the_model_gets_the_numbered_parts_the_question_and_the_tool(monkeypatch):
    client = FakeClient(GOOD)

    make(monkeypatch, client, chunks=TWO_PARTS)(QUESTION, "A-1")

    prompt, max_tokens, tool = client.calls[0]
    assert "[part 0]" in prompt and "The mesh has 200 cells." in prompt
    assert "[part 1]" in prompt and "The time step is 0.01 s." in prompt
    assert QUESTION in prompt
    assert max_tokens == CLAIMS_MAX_TOKENS
    assert tool.name == "list_claims"


def test_a_wrong_answer_is_sent_back_so_the_next_tier_writes_a_new_one(monkeypatch):
    client = FakeClient(GOOD)
    make(monkeypatch, client, chunks=TWO_PARTS)(QUESTION, "A-1")
    problem_with = client.hooks[0]

    def result(arguments):
        return LLMResult(text="{}", model="m", tier=1, arguments=arguments)

    def one(part, quote):
        return {"claims": [{"text": "x", "part": part, "quote": quote}]}

    assert problem_with(result(GOOD)) is None
    assert problem_with(result(None)) == "no arguments"
    assert "part 5" in problem_with(result(one(5, "mesh")))
    assert "quote" in problem_with(result(one(0, "it was never said")))


def test_an_unknown_artifact_becomes_the_api_error(monkeypatch):
    extract = make(monkeypatch, FakeClient(GOOD), error=UnknownArtifact("none"))

    with pytest.raises(UnknownArtifactId):
        extract(QUESTION, "A-missing")


def test_when_every_tier_fails_the_claims_error_says_so(monkeypatch):
    client = FakeClient(error=AllFreeTiersExhausted(()))

    with pytest.raises(ClaimsError, match="no tier"):
        make(monkeypatch, client, chunks=TWO_PARTS)(QUESTION, "A-1")


def test_an_answer_with_no_arguments_is_a_claims_error(monkeypatch):
    with pytest.raises(ClaimsError, match="no arguments"):
        make(monkeypatch, FakeClient(None), chunks=TWO_PARTS)(QUESTION, "A-1")


def test_a_reference_that_does_not_fit_is_refused_before_any_call(monkeypatch):
    client = FakeClient(GOOD)
    big = [chunk(0, "x" * 45_000), chunk(1, "x" * 45_000)]

    with pytest.raises(ClaimsError, match="does not fit"):
        make(monkeypatch, client, chunks=big)(QUESTION, "A-1")

    assert client.calls == []


def test_the_limit_in_code_is_above_the_number_the_instruction_asks_for():
    assert CLAIMS_WANTED < MAX_CLAIMS
