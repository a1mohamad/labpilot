"""The claims, the differences and the bugs, from stored rows to the answer.

The unit tests give these steps fake functions, and the api tests give them a
fake client and fake rows. So nothing proved the joins: the rows in Postgres
read back in order, the number the model writes turned into the place of a
stored part, the quote looked up in the part the model named, a wrong number
sent on to the next tier, and the findings that the answer reads and the saved
chat does not keep.

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
from labpilot.api import asking, reading, searching
from labpilot.api.checkpoints import open_saver
from labpilot.api.claims import make_claims_extractor
from labpilot.api.errors import EmbeddingUnavailable
from labpilot.api.finding_lines import BUGS_NOTE, DIFFERENCES_NOTE
from labpilot.llm import AllFreeTiersExhausted, GeminiProvider, LLMClient, LLMResult
from labpilot.prompts import SUMMARY_MAX_TOKENS
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

    [found] = extract(a)

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

    [found] = extract(a)

    assert found.source == STEP


@responses.activate
def test_the_request_carries_the_claims_tool_with_a_quote_for_every_claim(db):
    a, _ = store(db)
    responses.post(url("one"), json=called({"claims": [claim(1)]}))

    make_claims_extractor(db, LLMClient(chain=(provider("one", 1, pool="P1"),)))(a)

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

    [found] = make_claims_extractor(db, client)(a)

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

    [found] = make_claims_extractor(db, client)(a)

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
        extract(a)


class FindersClient:
    """Plans the steps it is given, then answers each tool by its name.

    It reads the numbered parts and facts out of the prompt, as a model would,
    and names the part that holds the words it is looking for. If the code
    numbered the parts differently from the way it looks them up, this client
    would name the wrong one and the quote would not be in it.
    """

    def __init__(self, steps=("find_differences",), judge="real", groups=()):
        self.steps = list(steps)
        self.judge = judge
        self.groups = [list(group) for group in groups]
        self.prompts = {}
        self.answers = []

    def part_with(self, prompt, words):
        marks = list(re.finditer(r"\[part (\d+)\]\n", prompt))
        for mark, after in zip(marks, [*marks[1:], None], strict=True):
            end = after.start() if after else len(prompt)
            if words in prompt[mark.end() : end]:
                return int(mark.group(1))
        raise AssertionError(f"no part holds {words!r}")

    def fact_number(self, prompt, words):
        return int(re.search(rf"(\d+)\. [^\n]*{re.escape(words)}", prompt).group(1))

    def result(self, arguments):
        return LLMResult(
            text="ok", model="fake", tier=1, finish_reason="STOP", arguments=arguments
        )

    def answer(self, name, prompt):
        if name == "make_plan":
            return {"steps": self.steps, "queries": []}
        if name == "judge_correspondence":
            return {"verdict": "PARTIAL", "reason": "they describe the same work"}
        if name == "list_claims":
            return {
                "claims": [
                    claim(self.part_with(prompt, "time step is 0.01 s")),
                    {
                        "text": "the mesh has 200 cells",
                        "part": self.part_with(prompt, "mesh has 200 cells"),
                        "quote": "mesh has 200 cells",
                    },
                ]
            }
        if name == "give_verdicts":
            return {
                "answers": [
                    {
                        "n": self.fact_number(prompt, "time step"),
                        "verdict": "differs",
                        "part": self.part_with(prompt, "dt = 0.05"),
                        "quote": "dt = 0.05",
                        "why": "B uses a bigger step",
                    },
                    {"n": self.fact_number(prompt, "mesh has"), "verdict": "same"},
                ]
            }
        if name == "list_items":
            return {"items": []}
        if name == "judge_findings":
            listed = prompt.split("FINDINGS", 1)[1]
            count = len(re.findall(r"^\d+\. ", listed, re.M))
            return {
                "answers": [
                    {"n": n, "verdict": self.judge, "relation": "differs", "why": ""}
                    for n in range(count)
                ]
            }
        if name == "group_findings":
            return {"groups": self.groups}
        if name == "list_defects":
            if "steps = 0" not in prompt:
                return {"defects": []}
            return {
                "defects": [
                    {
                        "kind": "logic",
                        "part": self.part_with(prompt, "steps = 0"),
                        "quote": "steps = 0",
                        "text": "the solver never takes a step",
                    }
                ]
            }
        if name == "list_obligations":
            return {"obligations": ["Does the solver take at least one step?"]}
        if name == "answer_checklist":
            return {"answers": [{"n": 0, "meets": "yes"}]}
        if name == "judge_suspects":
            return {"verdicts": [{"n": 0, "verdict": "real", "reason": "no step"}]}
        raise AssertionError(f"an unexpected tool: {name}")

    def generate(self, prompt, *, max_tokens=0, tool=None, problem_with=None):
        if tool is not None:
            self.prompts.setdefault(tool.name, []).append(prompt)
            return self.result(self.answer(tool.name, prompt))
        if max_tokens == SUMMARY_MAX_TOKENS:
            return LLMResult(text="a summary", model="fake", tier=1)
        self.answers.append(prompt)
        return LLMResult(text="an answer", model="fake", tier=1, finish_reason="STOP")


def store_with_a_bug(db):
    a, b = store(db)
    write_artifact(
        db,
        ArtifactRecord(id=b, name="solver.py", side="B", embedding_model=MODEL, dim=3),
        [
            row(0, SOLVER_MESH, "mesh = 200", "solver.py"),
            row(1, SOLVER_STEP, "dt = 0.05\nsteps = 0", "solver.py"),
        ],
    )
    return a, b


def ask(db, client, *, with_a_bug=False, **kwargs):
    a, b = store_with_a_bug(db) if with_a_bug else store(db)
    return asking.ask(db, a, b, question=QUESTION, client=client, **kwargs)


@pytest.fixture(autouse=True)
def embedded(monkeypatch):
    monkeypatch.setattr(searching, "_embed_question", lambda *a, **k: V)
    # The claims and the differences run on the search path only (R21): when
    # everything is read the answer sees both files whole. This small pair
    # would fit, so it is searched.
    monkeypatch.setattr(asking, "fits_whole", lambda *a, **k: False)


def test_a_fact_of_a_that_b_breaks_reaches_the_answer_with_its_place_in_b(db):
    client = FindersClient()

    ask(db, client)

    audit = client.prompts["give_verdicts"][0]
    assert "the time step is 0.01 s" in audit and "dt = 0.05" in audit
    answer = client.answers[0]
    assert DIFFERENCES_NOTE in answer
    assert (
        '[B differs] B uses a bigger step A states: "the time step is 0.01 s". '
        f'B ({SOLVER_STEP}): "dt = 0.05".'
    ) in answer
    assert "mesh has 200 cells" not in answer.split(DIFFERENCES_NOTE, 1)[1]


def test_the_scan_reads_the_whole_of_a_beside_b(db):
    client = FindersClient()

    ask(db, client)

    scan = client.prompts["list_items"][0]
    assert "The mesh has 200 cells." in scan and "The time step is 0.01 s." in scan
    assert "dt = 0.05" in scan


def test_a_difference_every_judge_calls_false_never_reaches_the_answer(db):
    client = FindersClient(judge="false")

    ask(db, client)

    assert DIFFERENCES_NOTE not in client.answers[0]


def test_when_no_tier_answers_the_differences_the_answer_goes_on_without_them(db):
    class Silent(FindersClient):
        def generate(self, prompt, *, max_tokens=0, tool=None, problem_with=None):
            if tool is not None and tool.name in ("give_verdicts", "list_items"):
                raise AllFreeTiersExhausted(())
            return super().generate(
                prompt, max_tokens=max_tokens, tool=tool, problem_with=problem_with
            )

    comparison = ask(db, Silent())

    assert comparison.result.text == "an answer"
    assert DIFFERENCES_NOTE not in comparison.prompt


def test_the_bugs_of_b_reach_the_answer_beside_the_differences(db):
    client = FindersClient(steps=("find_differences", "find_bugs"))

    ask(db, client, with_a_bug=True)

    answer = client.answers[0]
    assert BUGS_NOTE in answer
    assert "[real - logic] the solver never takes a step" in answer
    assert "[B differs] B uses a bigger step" in answer


def test_a_bug_that_makes_the_same_point_as_a_difference_is_shown_once(db):
    # The final merge numbers the differences first, then the bugs: 0 is the
    # difference and 1 the bug, and a group of both keeps the difference.
    client = FindersClient(steps=("find_differences", "find_bugs"), groups=[[0, 1]])

    ask(db, client, with_a_bug=True)

    answer = client.answers[0]
    assert "[B differs] B uses a bigger step" in answer
    assert "the solver never takes a step" not in answer


def test_the_saved_chat_keeps_no_claims_and_no_findings_after_the_message(
    db, chat_tables
):
    client = FindersClient(steps=("find_differences", "find_bugs"))
    config = {"configurable": {"thread_id": "chat-finders"}}

    ask(db, client, with_a_bug=True, thread_id="chat-finders")

    values = open_saver(db).get_tuple(config).checkpoint["channel_values"]
    assert not values.get("claims")
    assert not values.get("differences")
    assert not values.get("bugs")
    assert values["history"] == [QUESTION]


def test_a_search_that_fails_for_the_question_itself_still_stops_the_answer(
    db, monkeypatch
):
    def down(*_args, **_kwargs):
        raise EmbeddingUnavailable("the embedder is down")

    # Too small to stuff, so the planner's search path runs and it is not optional.
    monkeypatch.setattr(reading, "PROMPT_BUDGET", 1)
    monkeypatch.setattr(searching, "_embed_question", down)

    with pytest.raises(EmbeddingUnavailable):
        ask(db, FindersClient())


class HaltClient(FindersClient):
    """The gate says NONE: the two summaries do not correspond."""

    def answer(self, name, prompt):
        if name == "judge_correspondence":
            return {"verdict": "NONE", "reason": "they are about different things"}
        return super().answer(name, prompt)


def test_a_none_verdict_answers_from_the_two_summaries_and_the_chat_is_saved(
    db, chat_tables
):
    client = HaltClient()
    config = {"configurable": {"thread_id": "chat-halt"}}

    comparison = ask(db, client, thread_id="chat-halt")

    text = comparison.result.text
    assert comparison.result.model == "correspondence gate"
    assert "I did not compare these two" in text
    assert "they are about different things" in text
    assert "A: a summary" in text and "B: a summary" in text
    # nothing after the gate ran: no claims, no differences, no report
    assert "list_claims" not in client.prompts
    assert "give_verdicts" not in client.prompts
    assert client.answers == []
    assert comparison.chunks == ()
    assert comparison.prompt == ""
    values = open_saver(db).get_tuple(config).checkpoint["channel_values"]
    assert values["correspondence"].verdict == "NONE"
