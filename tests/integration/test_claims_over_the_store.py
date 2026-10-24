"""The claims and the checks, from stored rows to the answer.

The unit tests give the claim step and the check step fake functions, and the
api tests give them a fake client and fake rows. So nothing proved the joins:
the rows in Postgres read back in order, the number the model writes turned into
the place of a stored part, the quote looked up in the part the model named, a
wrong number sent on to the next tier, and the findings that the answer reads
and the saved chat does not keep.

`database` marked and free: no API quota. The first group uses the real provider
code with `responses` in place of the provider, and the second runs `ask()` with
a client that answers each tool by its name.
"""

from __future__ import annotations

import json
import re

import pytest
import responses

from labpilot.agent import ClaimsError
from labpilot.api import asking, searching
from labpilot.api.checkpoints import open_saver
from labpilot.api.claims import make_claims_extractor
from labpilot.llm import AllFreeTiersExhausted, GeminiProvider, LLMClient, LLMResult
from labpilot.prompts import CHECKS_NOTE, REQUERY, SUMMARY_MAX_TOKENS
from labpilot.store import ArtifactRecord, ChunkRecord, write_artifact

pytestmark = pytest.mark.database

MODEL = "codestral-embed"
V = (1.0, 0.0, 0.0)
BASE = "https://provider.test/v1beta/models"
QUESTION = "Why do the results differ?"

MESH = "[paper.md · 3 Method · lines 1-9]"
STEP = "[paper.md · 4 Setup · lines 10-19]"
SOLVER_MESH = "[solver.py · lines 1-9]"
SOLVER_STEP = "[solver.py · lines 10-19]"


def row(index, header, text, source):
    return ChunkRecord(
        chunk_index=index,
        text=text,
        header=header,
        source=source,
        start_line=index * 10 + 1,
        end_line=index * 10 + 9,
        vector=V,
    )


def store(db, *, reverse=False):
    paper = [
        row(0, MESH, "The mesh has 200 cells.", "paper.md"),
        row(1, STEP, "The time step is 0.01 s.", "paper.md"),
    ]
    code = [
        row(0, SOLVER_MESH, "mesh = 200", "solver.py"),
        row(1, SOLVER_STEP, "dt = 0.05", "solver.py"),
    ]
    for side, name, rows in (("A", "paper.md", paper), ("B", "solver.py", code)):
        write_artifact(
            db,
            ArtifactRecord(
                id=f"{side}-claims",
                name=name,
                side=side,
                embedding_model=MODEL,
                dim=3,
            ),
            rows[::-1] if reverse else rows,
        )
    return "A-claims", "B-claims"


def provider(model, tier, *, pool):
    return GeminiProvider(
        name=f"Tier {tier}",
        tier=tier,
        url=BASE,
        model=model,
        api_key_env="TEST_API_KEY",
        quota_pool=pool,
        context_window=1_000_000,
        max_output_tokens=64_000,
    )


def url(model):
    return f"{BASE}/{model}:generateContent"


def called(arguments, model="one"):
    return {
        "modelVersion": model,
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"functionCall": {"name": "list_claims", "args": arguments}}
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


def claim(part, quote="The time step is 0.01 s"):
    return {"text": "the time step is 0.01 s", "part": part, "quote": quote}


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", lambda _seconds: None)


def prompt_of(call):
    return json.loads(call.request.body)["contents"][0]["parts"][0]["text"]


@responses.activate
def test_the_number_the_model_writes_becomes_the_stored_header_of_that_part(db):
    a, _ = store(db)
    responses.post(url("one"), json=called({"claims": [claim(1)]}))
    extract = make_claims_extractor(
        db, LLMClient(chain=(provider("one", 1, pool="P1"),))
    )

    [found] = extract(QUESTION, a)

    assert found.source == STEP
    assert found.quote == "The time step is 0.01 s"
    sent = prompt_of(responses.calls[0])
    first = f"[part 0]\n{MESH}\nThe mesh has 200 cells."
    second = f"[part 1]\n{STEP}\nThe time step is 0.01 s."
    assert first in sent and second in sent
    assert sent.index(first) < sent.index(second)


@responses.activate
def test_the_parts_are_numbered_in_chunk_order_whatever_order_they_were_stored_in(db):
    a, _ = store(db, reverse=True)
    responses.post(url("one"), json=called({"claims": [claim(1)]}))
    extract = make_claims_extractor(
        db, LLMClient(chain=(provider("one", 1, pool="P1"),))
    )

    [found] = extract(QUESTION, a)

    assert found.source == STEP


@responses.activate
def test_the_request_carries_the_claims_tool_with_a_quote_for_every_claim(db):
    a, _ = store(db)
    responses.post(url("one"), json=called({"claims": [claim(1)]}))

    make_claims_extractor(db, LLMClient(chain=(provider("one", 1, pool="P1"),)))(
        QUESTION, a
    )

    tools = json.loads(responses.calls[0].request.body)["tools"]
    declaration = tools[0]["functionDeclarations"][0]
    item = declaration["parameters"]["properties"]["claims"]["items"]
    assert declaration["name"] == "list_claims"
    assert item["required"] == ["text", "part", "quote"]


@responses.activate
def test_a_part_number_that_does_not_exist_is_tried_again_on_the_next_tier(db):
    a, _ = store(db)
    responses.post(url("one"), json=called({"claims": [claim(9)]}))
    responses.post(url("two"), json=called({"claims": [claim(1)]}, "two"))
    client = LLMClient(
        chain=(provider("one", 1, pool="P1"), provider("two", 2, pool="P2"))
    )

    [found] = make_claims_extractor(db, client)(QUESTION, a)

    assert found.source == STEP
    assert [call.request.url for call in responses.calls] == [url("one"), url("two")]
    assert prompt_of(responses.calls[0]) == prompt_of(responses.calls[1])


@responses.activate
def test_a_quote_that_is_not_in_the_stored_part_is_tried_again_on_the_next_tier(db):
    a, _ = store(db)
    made_up = claim(1, "The time step is 0.5 s")
    responses.post(url("one"), json=called({"claims": [made_up]}))
    responses.post(url("two"), json=called({"claims": [claim(1)]}, "two"))
    client = LLMClient(
        chain=(provider("one", 1, pool="P1"), provider("two", 2, pool="P2"))
    )

    [found] = make_claims_extractor(db, client)(QUESTION, a)

    assert found.quote == "The time step is 0.01 s"
    assert len(responses.calls) == 2


@responses.activate
def test_when_every_tier_makes_up_its_quotes_there_are_no_claims(db):
    a, _ = store(db)
    made_up = claim(1, "it was never said")
    responses.post(url("one"), json=called({"claims": [made_up]}))
    extract = make_claims_extractor(
        db, LLMClient(chain=(provider("one", 1, pool="P1"),))
    )

    with pytest.raises(ClaimsError):
        extract(QUESTION, a)


class ClaimsClient:
    """Plans for the claims step, then answers each tool by its name.

    It reads the numbered parts out of the prompt, as a model would, and names
    the part that holds the words it is looking for. If the code numbered the
    parts differently from the way it looks them up, this client would name the
    wrong one and the quote would not be in it.
    """

    def __init__(self, verdict="mismatch"):
        self.verdict = verdict
        self.claim_prompts = []
        self.check_prompts = []
        self.answers = []

    def part_with(self, prompt, words):
        parts = re.findall(
            r"\[part (\d+)\]\n(.*?)(?=\n\n\[part|\n\nGive|\n\nList)", prompt, re.S
        )
        return next(int(number) for number, text in parts if words in text)

    def result(self, arguments):
        return LLMResult(
            text="ok", model="fake", tier=1, finish_reason="STOP", arguments=arguments
        )

    def generate(self, prompt, *, max_tokens=0, tool=None, problem_with=None):
        name = tool.name if tool else None
        if name == "make_plan":
            return self.result({"steps": ["extract_claims"], "queries": []})
        if name == "list_claims":
            self.claim_prompts.append(prompt)
            return self.result(
                {
                    "claims": [
                        claim(self.part_with(prompt, "time step is 0.01 s")),
                        {
                            "text": "the mesh has 200 cells",
                            "part": self.part_with(prompt, "mesh has 200 cells"),
                            "quote": "mesh has 200 cells",
                        },
                    ]
                }
            )
        if name == "give_verdict":
            self.check_prompts.append(prompt)
            if "time step" in prompt.split("THE PARTS", 1)[0]:
                part = self.part_with(prompt, "dt = 0.05")
                return self.result(
                    {
                        "verdict": self.verdict,
                        "kind": "choice",
                        "part": part,
                        "quote": "dt = 0.05",
                        "note": "B uses a bigger step",
                    }
                )
            part = self.part_with(prompt, "mesh = 200")
            return self.result(
                {
                    "verdict": "match",
                    "part": part,
                    "quote": "mesh = 200",
                    "note": "same",
                }
            )
        if max_tokens == SUMMARY_MAX_TOKENS:
            return LLMResult(text="a summary", model="fake", tier=1)
        self.answers.append(prompt)
        return LLMResult(text="an answer", model="fake", tier=1, finish_reason="STOP")


def ask(db, client, **kwargs):
    a, b = store(db)
    return asking.ask(db, a, b, question=QUESTION, client=client, **kwargs)


@pytest.fixture(autouse=True)
def embedded(monkeypatch):
    monkeypatch.setattr(searching, "_embed_question", lambda *a, **k: V)


def test_every_claim_is_checked_in_the_stored_other_file_and_the_answer_reads_it(db):
    client = ClaimsClient()

    ask(db, client)

    assert len(client.check_prompts) == 2
    assert len(client.answers) == 1
    answer = client.answers[0]
    assert CHECKS_NOTE in answer
    assert (
        f'[mismatch - choice] A says "the time step is 0.01 s" ({STEP}). '
        f'B ({SOLVER_STEP}): "dt = 0.05". B uses a bigger step'
    ) in answer
    assert (
        f'[match] A says "the mesh has 200 cells" ({MESH}). B ({SOLVER_MESH})' in answer
    )


def test_the_mismatch_is_listed_before_the_match_in_the_answer(db):
    client = ClaimsClient()

    ask(db, client)

    answer = client.answers[0]
    assert answer.index("\n[mismatch") < answer.index("\n[match]")


def test_a_check_that_no_tier_can_make_is_listed_as_unchecked_and_the_answer_goes_on(
    db,
):
    class NoChecks(ClaimsClient):
        def generate(self, prompt, *, max_tokens=0, tool=None, problem_with=None):
            if tool is not None and tool.name == "give_verdict":
                raise AllFreeTiersExhausted(())
            return super().generate(
                prompt, max_tokens=max_tokens, tool=tool, problem_with=problem_with
            )

    client = NoChecks()

    comparison = ask(db, client)

    assert comparison.result.text == "an answer"
    assert client.answers[0].count("\n[unchecked]") == 2


def test_the_saved_chat_keeps_no_claims_and_no_findings_after_the_message(
    db, chat_tables
):
    client = ClaimsClient()
    config = {"configurable": {"thread_id": "chat-claims"}}

    ask(db, client, thread_id="chat-claims")

    values = open_saver(db).get_tuple(config).checkpoint["channel_values"]
    assert not values.get("claims")
    assert not values.get("findings")
    assert values["history"] == [QUESTION]


class RetryClient(ClaimsClient):
    """The first check of the time step finds nothing, so the search is tried again.

    After that it answers as the plain client does, so the claim is checked a
    second time against whatever the new query found.
    """

    def __init__(self):
        super().__init__()
        self.requeries = []

    def generate(self, prompt, *, max_tokens=0, tool=None, problem_with=None):
        if tool is None and prompt.endswith(REQUERY.closing):
            self.requeries.append(prompt)
            return LLMResult(text="dt step", model="fake", tier=1)
        first_step_check = (
            tool is not None
            and tool.name == "give_verdict"
            and "time step" in prompt.split("THE PARTS", 1)[0]
            and not self.requeries
        )
        if first_step_check:
            self.check_prompts.append(prompt)
            return self.result(
                {"verdict": "absent", "note": "the parts do not show the step"}
            )
        return super().generate(
            prompt, max_tokens=max_tokens, tool=tool, problem_with=problem_with
        )


def test_an_absent_claim_is_searched_again_with_the_query_the_model_wrote(
    db, monkeypatch
):
    embedded = []
    monkeypatch.setattr(
        searching,
        "_embed_question",
        lambda text, **_: embedded.append(text) or V,
    )
    client = RetryClient()

    ask(db, client)

    assert len(client.requeries) == 1
    assert "the time step is 0.01 s" in client.requeries[0]
    assert "the parts do not show the step" in client.requeries[0]
    assert embedded.count("the time step is 0.01 s") == 1
    assert embedded.count("dt step") == 1
    answer = client.answers[0]
    assert f'[mismatch - choice] A says "the time step is 0.01 s" ({STEP})' in answer
    assert "\n[absent]" not in answer
