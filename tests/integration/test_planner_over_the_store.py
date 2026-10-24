"""The planner from stored rows to a plan, with only the provider's wire mocked.

tests/api/test_planning.py replaces `read_headers` and the client. The llm/ tests
replace the planner. So nothing proved the whole line: the rows in Postgres, the
SQL that cuts an opening out of them, the map, the request that leaves for the
provider, the function call that comes back, and the plan that is saved in a
chat. Each hop was tested alone, and these are the joins between them.

`database` marked and free: no API quota, because `responses` answers in place
of the provider.
"""

from __future__ import annotations

import json

import pytest
import responses

from labpilot.agent import Plan, Query, allowed_steps, build_graph
from labpilot.api import planning
from labpilot.api.checkpoints import open_saver
from labpilot.llm import GeminiProvider, LLMClient
from labpilot.store import ArtifactRecord, ChunkRecord, write_artifact

pytestmark = pytest.mark.database

MODEL = "codestral-embed"
V = (1.0, 0.0, 0.0)
BASE = "https://provider.test/v1beta/models"
QUESTION = "Why does my training code clip at 1.5 when the paper says 1.0?"

# These words sit where the map must NOT reach: the second paragraph of a
# docstring, text past the first 300 characters of a chunk, and the body of a
# later piece of a split function. The map shows a signature and ONE line, so if
# any of them shows up in the request, body text is leaking into the prompt.
IN_THE_DOCSTRING = "WORD_IN_THE_DOCSTRING"
BEYOND_THE_OPENING = "WORD_BEYOND_THE_OPENING"
IN_A_LATER_PART = "WORD_IN_A_LATER_PART"

GOOD = {
    "steps": ["extract_claims", "find_missing"],
    "queries": [
        {"side": "A", "text": "AdamW learning rate 3e-4"},
        {"side": "B", "text": "clip_grad_norm_ CLIP_NORM"},
    ],
}


def provider(model: str, tier: int, *, pool: str) -> GeminiProvider:
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


def url(model: str) -> str:
    return f"{BASE}/{model}:generateContent"


def called(arguments: dict, model: str = "planner-001") -> dict:
    return {
        "modelVersion": model,
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"functionCall": {"name": "make_plan", "args": arguments}}
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


def written(text: str, model: str = "planner-001") -> dict:
    return {
        "modelVersion": model,
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


def chunk(index: int, source: str, header: str, text: str) -> ChunkRecord:
    return ChunkRecord(
        chunk_index=index,
        text=text,
        header=header,
        source=source,
        start_line=index * 20 + 1,
        end_line=index * 20 + 19,
        vector=V,
    )


def store(db) -> tuple[str, str]:
    paper = [
        chunk(
            0,
            "paper.md",
            "[paper.md · 4.2 Optimization · lines 1-19]",
            "## 4.2 Optimization\n\nWe train with AdamW at a rate of 3e-4. More.\n",
        )
    ]
    code = [
        chunk(
            0,
            "train.py",
            "[train.py · class Trainer · def fit · part 1/2 · lines 1-19]",
            "def fit(self, loader, epochs=3):\n"
            '    """Runs the training loop.\n'
            f"\n    {IN_THE_DOCSTRING} explains more.\n"
            '    """\n' + "    # padding\n" * 30 + f"    {BEYOND_THE_OPENING} = 1\n",
        ),
        chunk(
            1,
            "train.py",
            "[train.py · class Trainer · def fit · part 2/2 · lines 20-39]",
            f"    {IN_A_LATER_PART} = 2\n",
        ),
        chunk(
            2,
            "train.py",
            "[train.py · def main · lines 40-59]",
            "def main():\n    pass\n",
        ),
    ]
    for side, name, rows in (("A", "paper.md", paper), ("B", "train.py", code)):
        write_artifact(
            db,
            ArtifactRecord(
                id=f"{side}-planner",
                name=name,
                side=side,
                embedding_model=MODEL,
                dim=3,
            ),
            rows,
        )
    return "A-planner", "B-planner"


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")
    monkeypatch.setattr("labpilot.llm.chain.time.sleep", lambda _seconds: None)


def request(call) -> dict:
    return json.loads(call.request.body)


def prompt_of(call) -> str:
    return request(call)["contents"][0]["parts"][0]["text"]


@responses.activate
def test_stored_rows_reach_the_provider_as_a_map_and_the_answer_becomes_a_plan(db):
    a, b = store(db)
    responses.post(url("one"), json=called(GOOD))
    planner = planning.make_planner(
        db, LLMClient(chain=(provider("one", 1, pool="P1"),))
    )

    plan = planner(QUESTION, a, b)

    assert plan == Plan(
        steps=("extract_claims", "find_missing"),
        queries=(
            Query("A", "AdamW learning rate 3e-4"),
            Query("B", "clip_grad_norm_ CLIP_NORM"),
        ),
    )
    sent = prompt_of(responses.calls[0])
    assert "def fit(self, loader, epochs=3)   lines 1-39" in sent
    assert '"Runs the training loop."' in sent
    assert '"We train with AdamW at a rate of 3e-4."' in sent
    assert "  def main()   lines 41-59" in sent
    # the provider adds its JSON instruction after the prompt, so the question
    # is last of OUR text and not last of the request
    assert f"THE QUESTION\n{QUESTION}" in sent


@responses.activate
def test_the_request_never_carries_body_text_only_a_signature_and_one_line(db):
    a, b = store(db)
    responses.post(url("one"), json=called(GOOD))

    planning.make_planner(db, LLMClient(chain=(provider("one", 1, pool="P1"),)))(
        QUESTION, a, b
    )

    sent = prompt_of(responses.calls[0])
    assert IN_THE_DOCSTRING not in sent
    assert BEYOND_THE_OPENING not in sent
    assert IN_A_LATER_PART not in sent


@responses.activate
def test_the_request_carries_the_tool_the_stored_pair_allows(db):
    a, b = store(db)
    responses.post(url("one"), json=called(GOOD))

    planning.make_planner(db, LLMClient(chain=(provider("one", 1, pool="P1"),)))(
        QUESTION, a, b
    )

    declaration = request(responses.calls[0])["tools"][0]["functionDeclarations"][0]
    steps = declaration["parameters"]["properties"]["steps"]["items"]["enum"]
    assert declaration["name"] == "make_plan"
    assert steps == list(allowed_steps(("A", "B")))


@responses.activate
def test_one_stored_file_gives_a_smaller_tool_and_a_map_of_one_side(db):
    _, b = store(db)
    responses.post(url("one"), json=called({"steps": ["find_missing"], "queries": []}))

    planning.make_planner(db, LLMClient(chain=(provider("one", 1, pool="P1"),)))(
        QUESTION, "", b
    )

    sent = prompt_of(responses.calls[0])
    declaration = request(responses.calls[0])["tools"][0]["functionDeclarations"][0]
    assert "SIDE A" not in sent
    assert "SIDE B" in sent
    assert declaration["parameters"]["properties"]["steps"]["items"]["enum"] == list(
        allowed_steps(("B",))
    )


@responses.activate
def test_a_wrong_plan_from_the_first_tier_is_tried_again_on_the_second(db):
    a, b = store(db)
    wrong = {"steps": ["fly_to_the_moon"], "queries": []}
    responses.post(url("one"), json=called(wrong))
    responses.post(url("two"), json=called(GOOD))
    planner = planning.make_planner(
        db,
        LLMClient(chain=(provider("one", 1, pool="P1"), provider("two", 2, pool="P2"))),
    )

    plan = planner(QUESTION, a, b)

    assert plan.steps == ("extract_claims", "find_missing")
    assert [call.request.url for call in responses.calls] == [url("one"), url("two")]
    assert (
        request(responses.calls[0])["contents"]
        == request(responses.calls[1])["contents"]
    ), "the next tier must get the same question and the same map"


@responses.activate
def test_a_tier_that_answers_in_a_code_fence_instead_of_a_call_still_gives_the_plan(
    db,
):
    # gemma-4 writes the JSON inside a fence even when asked for nothing else
    a, b = store(db)
    fenced = "```json\n" + json.dumps(GOOD) + "\n```"
    responses.post(url("one"), json=written(fenced))

    plan = planning.make_planner(db, LLMClient(chain=(provider("one", 1, pool="P1"),)))(
        QUESTION, a, b
    )

    assert plan.steps == ("extract_claims", "find_missing")
    assert plan.source == "planner"


def graph(planner, saver):
    return build_graph(
        measure=lambda a, b: "sides",
        fits=lambda sides, question: True,
        stuff=lambda sides, question: ((), None),
        search_one=lambda sides, query: (),
        totals_of=lambda sides: {"A": 1},
        rank_side=lambda question, pile: pile,
        make_prompt=lambda chunks, **_: ("the prompt", ()),
        generate=lambda prompt: "the result",
        plan=planner,
        checkpointer=saver,
    )


@responses.activate
def test_the_plan_is_saved_in_the_real_chat_memory_and_comes_back_as_a_plan(
    db, chat_tables
):
    a, b = store(db)
    responses.post(url("one"), json=called(GOOD))
    planner = planning.make_planner(
        db, LLMClient(chain=(provider("one", 1, pool="P1"),))
    )
    config = {"configurable": {"thread_id": "chat-planner"}}

    graph(planner, open_saver(db)).invoke(
        {"question": QUESTION, "a": a, "b": b}, config, durability="exit"
    )

    saved = open_saver(db).get_tuple(config).checkpoint["channel_values"]["plan"]
    assert isinstance(saved, Plan)
    assert [type(query) for query in saved.queries] == [Query, Query]
    assert list(saved.steps) == ["extract_claims", "find_missing"]
    assert saved.source == "planner"


@responses.activate
def test_the_second_message_of_a_chat_is_planned_again_and_replaces_the_plan(
    db, chat_tables
):
    a, b = store(db)
    second = {
        "steps": ["find_missing"],
        "queries": [{"side": "B", "text": "zero_grad"}],
    }
    responses.post(url("one"), json=called(GOOD))
    responses.post(url("one"), json=called(second))
    planner = planning.make_planner(
        db, LLMClient(chain=(provider("one", 1, pool="P1"),))
    )
    config = {"configurable": {"thread_id": "chat-replanned"}}
    compiled = graph(planner, open_saver(db))

    compiled.invoke({"question": "first?", "a": a, "b": b}, config, durability="exit")
    compiled.invoke({"question": "second?", "a": a, "b": b}, config, durability="exit")

    values = open_saver(db).get_tuple(config).checkpoint["channel_values"]
    assert list(values["plan"].steps) == ["find_missing"]
    assert values["history"] == ["first?", "second?"]
    assert len(responses.calls) == 2


@responses.activate
def test_a_planner_that_every_tier_fails_still_lets_the_chat_answer(db, chat_tables):
    a, b = store(db)
    responses.post(url("one"), json=written("I cannot help with that."))
    planner = planning.make_planner(
        db, LLMClient(chain=(provider("one", 1, pool="P1"),))
    )
    config = {"configurable": {"thread_id": "chat-no-plan"}}

    final = graph(planner, open_saver(db)).invoke(
        {"question": QUESTION, "a": a, "b": b}, config, durability="exit"
    )

    assert final["plan"].source == "default"
    assert final["result"] == "the result"
    saved = open_saver(db).get_tuple(config).checkpoint["channel_values"]["plan"]
    assert isinstance(saved, Plan)
    assert saved.source == "default"
