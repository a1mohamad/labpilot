import threading

import pytest

from labpilot.agent import RESULT, Claim, ClaimsError
from labpilot.api import claims
from labpilot.api.errors import UnknownArtifactId
from labpilot.llm import AllFreeTiersExhausted, LLMResult
from labpilot.prompts import CLAIMS_MAX_TOKENS
from labpilot.store import StoredChunk, UnknownArtifact

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
    def __init__(self, arguments=None, error=None, answers=None):
        self.arguments = arguments
        self.error = error
        self.answers = answers
        self.calls = []
        self.hooks = []
        self.lock = threading.Lock()

    def generate(self, prompt, *, max_tokens, tool=None, problem_with=None):
        with self.lock:
            self.calls.append((prompt, max_tokens, tool))
            self.hooks.append(problem_with)
        if self.answers is not None:
            arguments = self.answers(prompt)
            if isinstance(arguments, Exception):
                raise arguments
        elif self.error:
            raise self.error
        else:
            arguments = self.arguments
        return LLMResult(text="{}", model="fake-model", tier=1, arguments=arguments)


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

    assert extract("A-1") == (
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

    result = make(monkeypatch, FakeClient(arguments), chunks=parts)("A-1")

    assert result[0].source == "paper.md"


def test_the_model_gets_the_numbered_parts_and_the_tool_and_no_question(monkeypatch):
    client = FakeClient(GOOD)

    make(monkeypatch, client, chunks=TWO_PARTS)("A-1")

    prompt, max_tokens, tool = client.calls[0]
    assert "[part 0]" in prompt and "The mesh has 200 cells." in prompt
    assert "[part 1]" in prompt and "The time step is 0.01 s." in prompt
    assert "QUESTION" not in prompt
    assert max_tokens == CLAIMS_MAX_TOKENS
    assert tool.name == "list_claims"


def test_a_wrong_answer_is_sent_back_so_the_next_tier_writes_a_new_one(monkeypatch):
    client = FakeClient(GOOD)
    make(monkeypatch, client, chunks=TWO_PARTS)("A-1")
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
        extract("A-missing")


def test_when_every_tier_fails_the_claims_error_says_so(monkeypatch):
    client = FakeClient(error=AllFreeTiersExhausted(()))

    with pytest.raises(ClaimsError, match="no tier"):
        make(monkeypatch, client, chunks=TWO_PARTS)("A-1")


def test_an_answer_with_no_arguments_is_a_claims_error(monkeypatch):
    with pytest.raises(ClaimsError, match="no tier"):
        make(monkeypatch, FakeClient(None), chunks=TWO_PARTS)("A-1")


def test_a_reference_that_does_not_fit_is_refused_before_any_call(monkeypatch):
    client = FakeClient(GOOD)
    big = [chunk(0, "x" * 45_000), chunk(1, "x" * 45_000)]

    with pytest.raises(ClaimsError, match="too big"):
        make(monkeypatch, client, chunks=big)("A-1")

    assert client.calls == []


def test_a_reference_with_no_parts_is_refused_before_any_call(monkeypatch):
    client = FakeClient(GOOD)

    with pytest.raises(ClaimsError, match="no parts"):
        make(monkeypatch, client, chunks=())("A-1")

    assert client.calls == []


# Two groups: 18 parts of about 240 tokens each make two groups (parts 0-9 and
# 10-17), and the part numbers in each prompt restart at 0.
EIGHTEEN = [chunk(n, f"knob {n} is {n}0 units. " + "y" * 660) for n in range(18)]


def answer_for_group(prompt):
    first = int(prompt.split("knob ", 1)[1].split(" ", 1)[0])
    return {
        "claims": [
            {
                "text": f"knob {first} is {first}0",
                "part": 0,
                "quote": f"knob {first} is {first}0 units",
            },
            {
                "text": f"knob {first + 1} is {first + 1}0",
                "part": 1,
                "quote": f"knob {first + 1} is {first + 1}0 units",
                "kind": RESULT,
            },
        ]
    }


def test_a_big_reference_is_asked_in_groups_and_each_group_restarts_at_part_0(
    monkeypatch,
):
    client = FakeClient(answers=answer_for_group)

    found = make(monkeypatch, client, chunks=EIGHTEEN)("A-1")

    assert len(client.calls) == 2
    for prompt, _, _ in client.calls:
        assert "[part 0]" in prompt and "[part 10]" not in prompt
    # The second group's part 0 is part 10 of the reference.
    assert {c.source for c in found} == {
        "[paper.md · part 0]",
        "[paper.md · part 1]",
        "[paper.md · part 10]",
        "[paper.md · part 11]",
    }


def test_the_groups_are_asked_at_the_same_time(monkeypatch):
    barrier = threading.Barrier(2, timeout=5)

    def answers(prompt):
        barrier.wait()
        return answer_for_group(prompt)

    found = make(monkeypatch, FakeClient(answers=answers), chunks=EIGHTEEN)("A-1")

    assert len(found) == 4


def test_the_kind_of_each_claim_is_kept(monkeypatch):
    found = make(monkeypatch, FakeClient(answers=answer_for_group), chunks=EIGHTEEN)(
        "A-1"
    )

    assert [c.kind for c in found].count(RESULT) == 2


def test_a_group_that_fails_loses_only_its_own_claims(monkeypatch, caplog):
    def answers(prompt):
        if "knob 0 " in prompt:
            return AllFreeTiersExhausted(())
        return answer_for_group(prompt)

    found = make(monkeypatch, FakeClient(answers=answers), chunks=EIGHTEEN)("A-1")

    assert {c.source for c in found} == {"[paper.md · part 10]", "[paper.md · part 11]"}
    assert "1 of 2 groups are missing" in caplog.text
