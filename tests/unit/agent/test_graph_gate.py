import pytest
from langgraph.checkpoint.memory import InMemorySaver

from labpilot.agent import Correspondence, GateError, Plan, build_graph
from labpilot.ingest import Chunk

SIDES = {"A": "stored A", "B": "stored B"}
NO_QUERY = Plan(steps=(), queries=())
PARTIAL = Correspondence("PARTIAL", "they share a goal")
NONE = Correspondence("NONE", "one is about memory, the other about images")


def chunk(index):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index + 1,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
    )


STUFFED = (chunk(900), chunk(901))


def build(verdicts, calls, *, with_gate=True, **extra):
    """A graph made of fakes. `verdicts` is what the gate gives, one for each call."""
    answers = iter(verdicts)

    def plan(question, a, b):
        calls.append("plan")
        return NO_QUERY

    def summarize(artifact_id):
        calls.append(f"summarize {artifact_id}")
        return f"summary of {artifact_id}"

    def gate(summary_a, summary_b):
        calls.append(("gate", summary_a, summary_b))
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def halt_answer(summary_a, summary_b, reason):
        calls.append(("halt", summary_a, summary_b, reason))
        return "the halt answer"

    def measure(a, b):
        calls.append("measure")
        return SIDES

    def make_prompt(chunks, question, totals, summaries, files, last_answer):
        calls.append("make_prompt")
        return "the prompt", chunks[:1]

    def generate(prompt):
        calls.append("generate")
        return "the result"

    options = {"gate": gate, "halt_answer": halt_answer} if with_gate else {}
    return build_graph(
        measure=measure,
        fits=lambda sides, question: True,
        stuff=lambda sides, question: (STUFFED, None),
        search_one=lambda sides, query: (),
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=lambda question, pile: pile,
        plan=plan,
        summarize=summarize,
        make_prompt=make_prompt,
        generate=generate,
        **options,
        **extra,
    )


START = {"question": "why?", "a": "A-1", "b": "B-1"}


def names(calls):
    return [call if isinstance(call, str) else call[0] for call in calls]


def test_a_partial_verdict_goes_on_to_the_answer():
    calls = []

    final = build([PARTIAL], calls).invoke(START)

    assert "halt" not in names(calls)
    assert names(calls)[-3:] == ["measure", "make_prompt", "generate"]
    assert final["result"] == "the result"
    assert final["correspondence"] == PARTIAL


def test_the_gate_waits_for_both_summaries_and_measure_waits_for_the_gate():
    calls = []

    build([PARTIAL], calls).invoke(START)

    order = names(calls)
    gate_at = order.index("gate")
    assert gate_at > order.index("summarize A-1")
    assert gate_at > order.index("summarize B-1")
    assert order.index("measure") > gate_at
    assert order.index("measure") > order.index("plan")


def test_the_gate_reads_the_two_summaries_of_this_message():
    calls = []

    build([PARTIAL], calls).invoke(START)

    assert ("gate", "summary of A-1", "summary of B-1") in calls


def test_a_none_verdict_stops_before_anything_is_searched_or_written():
    calls = []

    final = build([NONE], calls).invoke(START)

    assert not {"measure", "make_prompt", "generate"} & set(names(calls))
    assert ("halt", "summary of A-1", "summary of B-1", NONE.reason) in calls
    assert final["result"] == "the halt answer"


def test_the_planner_still_runs_when_the_gate_halts():
    calls = []

    build([NONE], calls).invoke(START)

    assert calls.count("plan") == 1


def test_a_halt_is_remembered_like_any_other_answer():
    final = build([NONE], []).invoke(START)

    assert final["history"] == ["why?"]


def test_a_halt_gives_ask_the_four_keys_it_reads():
    final = build([NONE], []).invoke(START)

    assert final["chunks"] == ()
    assert final["selected"] == ()
    assert final["prompt"] == ""
    assert final["totals"] is None


def test_a_halt_after_a_normal_message_does_not_keep_the_old_chunks():
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "chat-1"}}
    graph = build([PARTIAL, NONE], [], checkpointer=saver)

    first = graph.invoke(START, config)
    second = graph.invoke(START, config)

    assert first["chunks"] == STUFFED
    assert second["chunks"] == ()
    assert second["prompt"] == ""


def test_a_gate_that_cannot_judge_lets_the_run_go_on():
    calls = []

    final = build([GateError("every tier failed")], calls).invoke(START)

    assert names(calls)[-1] == "generate"
    assert final["correspondence"] is None


def test_an_old_verdict_never_decides_a_later_message():
    calls = []
    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "chat-1"}}
    graph = build([NONE, GateError("every tier failed")], calls, checkpointer=saver)

    first = graph.invoke(START, config)
    second = graph.invoke(START, config)

    assert first["result"] == "the halt answer"
    assert second["result"] == "the result"
    assert second["correspondence"] is None


@pytest.mark.parametrize(
    "start",
    [
        {"question": "why?", "a": "A-1", "b": ""},
        {"question": "why?", "a": "", "b": "B-1"},
        {"question": "why?", "a": "", "b": ""},
    ],
)
def test_with_fewer_than_two_files_the_gate_is_never_asked(start):
    calls = []

    final = build([NONE], calls).invoke(start)

    assert "gate" not in names(calls)
    assert final["correspondence"] is None
    assert names(calls)[-1] == "generate"


def test_without_a_gate_the_graph_is_the_one_it_was():
    calls = []

    build([], calls, with_gate=False).invoke(START)

    assert "gate" not in names(calls)
    assert "halt" not in names(calls)
    assert names(calls)[-1] == "generate"


def bare(**options):
    return build_graph(
        measure=None,
        fits=None,
        stuff=None,
        search_one=None,
        totals_of=None,
        rank_side=None,
        plan=None,
        make_prompt=None,
        generate=None,
        **options,
    )


def test_a_gate_needs_summaries_to_read():
    with pytest.raises(ValueError, match="summarize"):
        bare(gate=lambda a, b: PARTIAL, halt_answer=lambda a, b, reason: "")


def test_a_gate_needs_a_halt_answer():
    with pytest.raises(ValueError, match="halt_answer"):
        bare(summarize=lambda artifact_id: "", gate=lambda a, b: PARTIAL)


def test_a_halt_answer_without_a_gate_is_a_mistake():
    with pytest.raises(ValueError, match="gate"):
        bare(summarize=lambda artifact_id: "", halt_answer=lambda a, b, reason: "")
