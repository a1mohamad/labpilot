import pytest

from labpilot.agent import (
    PLAN_TOOL_NAME,
    Plan,
    PlanError,
    Query,
    allowed_steps,
    build_graph,
)
from labpilot.api import planning
from labpilot.api.errors import UnknownArtifactId
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMResult
from labpilot.prompts import PLANNER, PLANNER_INPUT_LIMIT, PLANNER_MAX_TOKENS
from labpilot.store import StoredHeader, UnknownArtifact
from labpilot.tokens import estimate_tokens

QUESTION = "Why does my model clip gradients at 1.5 when the paper says 1.0?"
GOOD = {
    "steps": ["extract_claims", "find_bugs"],
    "queries": [
        {"side": "A", "text": "gradient clipping value 1.0"},
        {"side": "B", "text": "clip_grad_norm_ CLIP_NORM"},
    ],
}


def header(index, source="train.py"):
    first = index * 10 + 1
    return StoredHeader(
        chunk_index=index,
        source=source,
        start_line=first,
        end_line=first + 9,
        header=f"[{source} · def step_{index} · lines {first}-{first + 9}]",
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


STORED = {
    "A-1": (header(0, "paper.md"), header(1, "paper.md")),
    "B-1": (header(0, "train.py"), header(1, "model.py")),
}


def make(monkeypatch, client, stored=None, error=None):
    def fake_read(conn, artifact_id):
        if error:
            raise error
        return (stored or STORED)[artifact_id]

    monkeypatch.setattr(planning, "read_headers", fake_read)
    return planning.make_planner(object(), client)


def test_the_arguments_of_the_model_become_the_plan(monkeypatch):
    plan = make(monkeypatch, FakeClient(GOOD))(QUESTION, "A-1", "B-1")

    assert plan == Plan(
        steps=("extract_claims", "find_bugs"),
        queries=(
            Query("A", "gradient clipping value 1.0"),
            Query("B", "clip_grad_norm_ CLIP_NORM"),
        ),
    )
    assert plan.source == "planner"


def test_with_no_file_at_all_no_model_is_asked(monkeypatch):
    client = FakeClient(error=AssertionError("the planner must not ask a model"))

    plan = make(monkeypatch, client)(QUESTION, "", "")

    assert client.calls == []
    assert plan.steps == ()
    assert plan.queries == ()


def test_the_model_gets_the_tool_the_files_allow(monkeypatch):
    client = FakeClient(GOOD)

    make(monkeypatch, client)(QUESTION, "A-1", "B-1")

    _, max_tokens, tool = client.calls[0]
    steps = tool.parameters["properties"]["steps"]["items"]["enum"]
    assert tool.name == PLAN_TOOL_NAME
    assert steps == list(allowed_steps(("A", "B")))
    assert max_tokens == PLANNER_MAX_TOKENS


def test_one_file_means_a_smaller_tool(monkeypatch):
    client = FakeClient({"steps": ["find_bugs"], "queries": []})

    make(monkeypatch, client)(QUESTION, "", "B-1")

    tool = client.calls[0][2]
    properties = tool.parameters["properties"]
    assert properties["steps"]["items"]["enum"] == list(allowed_steps(("B",)))
    assert properties["queries"]["items"]["properties"]["side"]["enum"] == ["B"]


def test_each_side_of_the_map_shows_the_file_of_its_own_artifact(monkeypatch):
    client = FakeClient(GOOD)

    make(monkeypatch, client)(QUESTION, "A-1", "B-1")

    prompt = client.calls[0][0]
    side_a, side_b = prompt.split("SIDE B")
    assert "paper.md" in side_a
    assert "train.py" not in side_a
    assert "train.py" in side_b
    assert "model.py" in side_b
    assert prompt.startswith(PLANNER)
    assert prompt.endswith(QUESTION)


def test_the_tool_name_is_the_one_the_instruction_talks_about():
    assert PLAN_TOOL_NAME in PLANNER


@pytest.mark.parametrize("question_size", [60, 30_000], ids=["short", "long"])
def test_the_map_is_cut_so_the_whole_call_fits_the_tightest_tier(
    monkeypatch, question_size
):
    client = FakeClient(GOOD)
    big = tuple(header(i, f"module_{i // 3}.py") for i in range(1_200))
    question = "why " * (question_size // 4)

    make(monkeypatch, client, {"A-1": big, "B-1": big})(question, "A-1", "B-1")

    prompt, _, tool = client.calls[0]
    schema = estimate_tokens(str(tool.parameters))
    assert estimate_tokens(prompt) + 2 * schema <= PLANNER_INPUT_LIMIT


@pytest.mark.parametrize(
    "arguments",
    [None, {}, {"steps": "find_bugs", "queries": []}],
    ids=["no arguments", "empty", "wrong shape"],
)
def test_an_answer_that_is_not_a_plan_is_a_plan_error(monkeypatch, arguments):
    with pytest.raises(PlanError):
        make(monkeypatch, FakeClient(arguments))(QUESTION, "A-1", "B-1")


def test_when_every_tier_fails_it_is_a_plan_error_and_not_a_503(monkeypatch):
    client = FakeClient(error=AllFreeTiersExhausted(()))

    with pytest.raises(PlanError, match="no tier gave a good plan"):
        make(monkeypatch, client)(QUESTION, "A-1", "B-1")


def test_an_artifact_that_is_not_stored_becomes_the_api_error(monkeypatch):
    planner = make(monkeypatch, FakeClient(GOOD), error=UnknownArtifact("none"))

    with pytest.raises(UnknownArtifactId):
        planner(QUESTION, "A-missing", "B-1")


class FakeProvider:
    def __init__(self, tier, arguments):
        self.name = f"Tier {tier}"
        self.tier = tier
        self.api_key_env = f"KEY_{tier}"
        self.arguments = arguments
        self.calls = []

    @property
    def pool(self):
        return self.api_key_env

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        self.calls.append((prompt, tool))
        return LLMResult(
            text="{}", model=self.name, tier=self.tier, arguments=self.arguments
        )


WRONG = [
    pytest.param(None, id="no arguments"),
    pytest.param({"steps": "find_bugs", "queries": []}, id="wrong shape"),
    pytest.param({"steps": ["fly_to_the_moon"], "queries": []}, id="unknown step"),
    pytest.param(
        {"steps": [], "queries": [{"side": "C", "text": "x"}]}, id="side with no file"
    ),
]


@pytest.mark.parametrize("arguments", WRONG)
def test_the_chain_is_told_to_reject_a_plan_the_files_do_not_allow(
    monkeypatch, arguments
):
    client = FakeClient(GOOD)
    make(monkeypatch, client)(QUESTION, "A-1", "B-1")

    reject = client.hooks[0]

    assert reject(LLMResult(text="{}", model="m", tier=1, arguments=GOOD)) is None
    assert (
        reject(LLMResult(text="{}", model="m", tier=1, arguments=arguments)) is not None
    )


def test_a_step_one_file_does_not_allow_is_rejected(monkeypatch):
    client = FakeClient({"steps": ["find_bugs"], "queries": []})
    make(monkeypatch, client)(QUESTION, "", "B-1")

    reject = client.hooks[0]
    claims = {"steps": ["extract_claims"], "queries": []}

    assert reject(LLMResult(text="{}", model="m", tier=1, arguments=claims))


@pytest.mark.parametrize("arguments", WRONG)
def test_a_wrong_plan_gets_a_chance_on_the_next_tier(monkeypatch, arguments):
    first, second = FakeProvider(1, arguments), FakeProvider(2, GOOD)
    planner = make(monkeypatch, LLMClient(chain=(first, second)))

    plan = planner(QUESTION, "A-1", "B-1")

    assert plan.source == "planner"
    assert plan.steps == ("extract_claims", "find_bugs")
    assert (len(first.calls), len(second.calls)) == (1, 1)


def test_the_next_tier_gets_the_same_question_and_the_same_tool(monkeypatch):
    first, second = FakeProvider(1, None), FakeProvider(2, GOOD)

    make(monkeypatch, LLMClient(chain=(first, second)))(QUESTION, "A-1", "B-1")

    assert first.calls == second.calls


def test_a_good_plan_stops_the_walk(monkeypatch):
    first, second = FakeProvider(1, GOOD), FakeProvider(2, GOOD)

    make(monkeypatch, LLMClient(chain=(first, second)))(QUESTION, "A-1", "B-1")

    assert len(second.calls) == 0


def test_when_every_tier_gives_a_wrong_plan_it_is_a_plan_error(monkeypatch):
    chain = tuple(FakeProvider(tier, None) for tier in range(1, 4))

    with pytest.raises(PlanError, match="no tier gave a good plan"):
        make(monkeypatch, LLMClient(chain=chain))(QUESTION, "A-1", "B-1")

    assert [len(provider.calls) for provider in chain] == [1, 1, 1]


def test_wrong_plans_do_not_walk_the_whole_chain(monkeypatch):
    chain = tuple(FakeProvider(tier, None) for tier in range(1, 8))

    with pytest.raises(PlanError):
        make(monkeypatch, LLMClient(chain=chain))(QUESTION, "A-1", "B-1")

    assert sum(len(provider.calls) for provider in chain) == 3


def run_graph(plan):
    graph = build_graph(
        measure=lambda a, b: object(),
        fits=lambda sides, question: True,
        stuff=lambda sides, question: (("whole",), None),
        search=lambda sides, question: (("found",), {"A": 1}),
        make_prompt=lambda chunks, question, totals: ("the prompt", chunks),
        generate=lambda prompt: "the result",
        plan=plan,
    )
    return graph.invoke({"question": QUESTION, "a": "A-1", "b": "B-1"})


def test_a_good_plan_goes_through_the_graph(monkeypatch):
    final = run_graph(make(monkeypatch, FakeClient(GOOD)))

    assert final["plan"].source == "planner"
    assert final["plan"].steps == ("extract_claims", "find_bugs")
    assert final["result"] == "the result"


def test_a_step_that_does_not_exist_becomes_the_default_plan(monkeypatch):
    bad = {"steps": ["fly_to_the_moon"], "queries": []}

    final = run_graph(make(monkeypatch, FakeClient(bad)))

    assert final["plan"].source == "default"
    assert final["plan"].steps == allowed_steps(("A", "B"))
    assert final["result"] == "the result"


def test_a_planner_that_is_down_never_stops_the_answer(monkeypatch):
    down = FakeClient(error=AllFreeTiersExhausted(()))

    final = run_graph(make(monkeypatch, down))

    assert final["plan"].source == "default"
    assert final["plan"].queries == (Query("A", QUESTION), Query("B", QUESTION))
    assert final["result"] == "the result"
