"""The graph reports each node, and a model call names the node that made it."""

from labpilot.agent import Plan, build_graph
from labpilot.ingest import Chunk
from labpilot.llm import LLMClient, LLMResult
from labpilot.timing import collecting

NO_QUERY = Plan(steps=(), queries=())


class Provider:
    api_key_env = "KEY"
    name = "Fake"
    tier = 1
    pool = "KEY"

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        return LLMResult(text="ok", model=self.name, tier=self.tier)


def run_graph():
    client = LLMClient(chain=(Provider(),))
    chunk = Chunk(
        text="t",
        source="a.py",
        start_line=1,
        end_line=2,
        side="B",
        artifact_id="B-1",
        chunk_index=0,
    )

    def summarize(artifact_id):
        return client.generate(f"summarize {artifact_id}").text

    graph = build_graph(
        measure=lambda a, b: {"A": "x", "B": "y"},
        fits=lambda sides, question, last_answer: True,
        stuff=lambda sides, question: ((chunk,), None),
        search_one=lambda sides, query: (chunk,),
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: NO_QUERY,
        make_prompt=lambda chunks, **_: ("prompt", chunks),
        generate=lambda prompt: client.generate(prompt),
        summarize=summarize,
    )
    with collecting() as collector:
        graph.invoke({"question": "q", "a": "A-1", "b": "B-1"})
    return collector.records


def test_every_node_that_ran_reports_its_seconds():
    steps = {r["name"] for r in run_graph() if r["kind"] == "step"}

    assert steps == {
        "plan",
        "summarize_a",
        "summarize_b",
        "measure",
        "stuff",
        "respond",
        "remember",
    }


def test_a_call_names_the_node_even_when_langgraph_runs_it_in_its_own_thread():
    calls = [r for r in run_graph() if r["kind"] == "call"]

    assert sorted(c["step"] for c in calls) == [
        "respond",
        "summarize_a",
        "summarize_b",
    ]


def test_the_steps_that_start_together_end_before_measure_starts():
    steps = {r["name"]: r for r in run_graph() if r["kind"] == "step"}

    ended = max(steps[n]["end"] for n in ("plan", "summarize_a", "summarize_b"))
    assert steps["measure"]["start"] >= ended - 0.001
