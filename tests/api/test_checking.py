import pytest

from labpilot.agent import CheckError, Claim
from labpilot.api.checking import make_checker
from labpilot.ingest import Chunk
from labpilot.llm import AllFreeTiersExhausted, LLMResult
from labpilot.prompts import CHECK_MAX_TOKENS

CLAIM = Claim("the time step is 0.01 s", "[paper.md · 4 Setup]", "time step is 0.01 s")
GOOD = {
    "verdict": "mismatch",
    "kind": "choice",
    "part": 1,
    "quote": "dt = 0.05",
    "note": "B uses a bigger step",
}


def chunk(index, text, *, header="x"):
    return Chunk(
        text=text,
        source="solver.py",
        start_line=index,
        end_line=index,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
        header=f"[solver.py · part {index}]" if header == "x" else header,
    )


PARTS = (chunk(0, "mesh = 200"), chunk(1, "dt = 0.05"))


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


def test_the_finding_gets_the_place_of_the_part_the_model_named():
    check = make_checker(FakeClient(GOOD))

    finding = check(CLAIM, PARTS)

    assert finding.claim == CLAIM
    assert (finding.verdict, finding.kind) == ("mismatch", "choice")
    assert finding.source == "[solver.py · part 1]"
    assert finding.quote == "dt = 0.05"


def test_a_part_without_a_header_gets_the_name_of_its_file():
    parts = (chunk(0, "mesh = 200"), chunk(1, "dt = 0.05", header=""))

    finding = make_checker(FakeClient(GOOD))(CLAIM, parts)

    assert finding.source == "solver.py"


def test_the_model_gets_the_claim_the_numbered_parts_and_the_tool():
    client = FakeClient(GOOD)

    make_checker(client)(CLAIM, PARTS)

    prompt, max_tokens, tool = client.calls[0]
    assert "the time step is 0.01 s" in prompt and "[paper.md · 4 Setup]" in prompt
    assert "[part 0]" in prompt and "mesh = 200" in prompt
    assert "[part 1]" in prompt and "dt = 0.05" in prompt
    assert max_tokens == CHECK_MAX_TOKENS
    assert tool.name == "give_verdict"


def test_a_wrong_answer_is_sent_back_so_the_next_tier_writes_a_new_one():
    client = FakeClient(GOOD)
    make_checker(client)(CLAIM, PARTS)
    problem_with = client.hooks[0]

    def result(arguments):
        return LLMResult(text="{}", model="m", tier=1, arguments=arguments)

    assert problem_with(result(GOOD)) is None
    assert problem_with(result(None)) == "no arguments"
    # A quote that is not in its part no longer sends the answer on (R6).
    assert problem_with(result({**GOOD, "quote": "dt = 0.5"})) is None
    assert "verdict" in problem_with(result({**GOOD, "verdict": "maybe"}))


def test_when_every_tier_fails_the_check_error_says_so():
    client = FakeClient(error=AllFreeTiersExhausted(()))

    with pytest.raises(CheckError, match="no tier"):
        make_checker(client)(CLAIM, PARTS)


def test_an_answer_with_no_arguments_is_a_check_error():
    with pytest.raises(CheckError, match="no arguments"):
        make_checker(FakeClient(None))(CLAIM, PARTS)
