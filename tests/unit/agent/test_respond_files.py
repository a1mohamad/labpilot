import pytest

from labpilot.agent import Plan, build_graph
from labpilot.agent.respond import make_respond_node
from labpilot.agent.summarize import make_summarize_node


def recorder():
    calls = []

    def make_prompt(chunks, question, totals, summaries, files, last_answer):
        calls.append((files, last_answer, summaries))
        return f"prompt for {files} files", chunks

    return calls, make_prompt


def state(a, b, last_answer="1. a  2. b"):
    return {
        "question": "why?",
        "a": a,
        "b": b,
        "chunks": (),
        "totals": None,
        "summary_a": "sum a",
        "last_answer": last_answer,
    }


# ---- the respond node alone -------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "files"),
    [("A-1", "B-1", 2), ("A-1", "", 1), ("", "B-1", 1), ("", "", 0)],
)
def test_the_number_of_files_is_counted_from_the_two_ids(a, b, files):
    calls, make_prompt = recorder()
    node = make_respond_node(make_prompt, lambda prompt: prompt)

    result = node(state(a, b))

    assert [call[0] for call in calls] == [files]
    assert result["result"] == f"prompt for {files} files"


@pytest.mark.parametrize(("a", "b"), [("A-1", "B-1"), ("A-1", ""), ("", "")])
def test_the_last_answer_and_the_summaries_reach_the_prompt_for_every_case(a, b):
    calls, make_prompt = recorder()
    node = make_respond_node(make_prompt, lambda prompt: prompt)

    node(state(a, b))

    assert calls[0][1:] == ("1. a  2. b", {"A": "sum a", "B": ""})


def test_a_state_with_no_last_answer_gives_an_empty_one():
    calls, make_prompt = recorder()
    node = make_respond_node(make_prompt, lambda prompt: prompt)
    chat_saved_before = {
        "question": "why?",
        "a": "",
        "b": "",
        "chunks": (),
        "totals": None,
    }

    node(chat_saved_before)

    assert calls[0][1] == ""


# ---- the summary node -------------------------------------------------------


def test_an_empty_id_is_not_summarized():
    seen = []
    node = make_summarize_node("b", lambda artifact_id: seen.append(artifact_id))

    assert node({"a": "A-1", "b": ""}) == {}
    assert seen == []


# ---- inside the real graph --------------------------------------------------


def run(a, b, *, last_answer=""):
    calls, make_prompt = recorder()
    summaries_asked = []

    def summarize(artifact_id):
        summaries_asked.append(artifact_id)
        return f"summary of {artifact_id}"

    graph = build_graph(
        measure=lambda x, y: {} if not (x or y) else {"B": "stored"},
        fits=lambda sides, question: True,
        stuff=lambda sides, question: ((), None),
        search_one=lambda sides, query: (),
        totals_of=lambda sides: {},
        rank_side=lambda question, pile: pile,
        plan=lambda question, x, y: Plan(steps=(), queries=()),
        make_prompt=make_prompt,
        generate=lambda prompt: "the result",
        summarize=summarize,
    )
    final = graph.invoke(
        {"question": "why?", "a": a, "b": b, "last_answer": last_answer}
    )
    return final, calls, sorted(summaries_asked)


def test_a_graph_with_no_file_summarizes_nothing_and_answers_with_zero_files():
    final, calls, summaries_asked = run("", "", last_answer="1. a  2. b")

    assert summaries_asked == []
    assert [call[:2] for call in calls] == [(0, "1. a  2. b")]
    assert final["prompt"] == "prompt for 0 files"


def test_a_graph_with_one_file_summarizes_only_that_file():
    final, calls, summaries_asked = run("A-1", "")

    assert summaries_asked == ["A-1"]
    assert [call[0] for call in calls] == [1]
    assert final["summary_a"] == "summary of A-1"
    assert "summary_b" not in final


def test_a_graph_with_two_files_summarizes_both_and_asks_for_two_files():
    final, calls, summaries_asked = run("A-1", "B-1")

    assert summaries_asked == ["A-1", "B-1"]
    assert [call[0] for call in calls] == [2]
