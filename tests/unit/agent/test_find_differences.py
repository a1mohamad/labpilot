import logging
import threading

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Overwrite

from labpilot.agent import (
    Bug,
    Claim,
    Difference,
    DifferencesError,
    Plan,
    Query,
    build_graph,
)
from labpilot.agent.final_merge import make_final_merge_node
from labpilot.agent.find_differences import (
    differences_task,
    make_find_differences_node,
    wants_differences,
)
from labpilot.ingest import Chunk

FOUND = Difference("differs", "B uses 64", "[train.py]", "batch = 64")
BUG = Bug("logic", "the loss is never reduced", "[train.py]", "loss.sum()")
BOTH = Plan(steps=("find_differences", "find_bugs"), queries=(Query("B", "the batch"),))
CLAIMS = (
    Claim("the batch is 128", "[paper.md]", "batch is 128"),
    Claim("F1 is 0.85", "[paper.md]", "F1 is 0.85", kind="result"),
)


def chunk(index):
    return Chunk(
        text=f"text {index}",
        source="train.py",
        start_line=index,
        end_line=index,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
    )


def test_only_the_method_claims_become_facts_of_a():
    task = differences_task({"a": "A-1", "b": "B-1", "claims": CLAIMS})

    assert task == {"a": "A-1", "b": "B-1", "facts": ("the batch is 128",)}


@pytest.mark.parametrize(
    ("a", "b", "steps", "wanted"),
    [
        ("A-1", "B-1", ("find_differences",), True),
        ("A-1", "B-1", ("find_bugs",), False),
        ("", "B-1", ("find_differences",), False),
    ],
)
def test_the_differences_need_two_files_and_the_step(a, b, steps, wanted):
    state = {"a": a, "b": b, "plan": Plan(steps=steps, queries=())}

    assert wants_differences(state) is wanted


def test_a_failed_finder_gives_no_differences_and_logs_why(caplog):
    def fails(a, b, facts):
        raise DifferencesError("no tier answered")

    node = make_find_differences_node(fails)
    with caplog.at_level(logging.WARNING):
        got = node({"a": "A-1", "b": "B-1", "facts": ()})

    assert got == {"differences": []}
    assert "no tier answered" in caplog.text


def test_any_other_error_reaches_the_caller_unchanged():
    def bug_of_ours(a, b, facts):
        raise TypeError("a bug")

    with pytest.raises(TypeError):
        make_find_differences_node(bug_of_ours)({"a": "A", "b": "B", "facts": ()})


def test_the_final_merge_hides_a_bug_that_makes_the_point_of_a_difference():
    other = Bug("code", "it divides by zero", "[train.py]", "x / n")
    node = make_final_merge_node(lambda lines: [[1, 0]])

    out = node({"differences": [FOUND], "bugs": [BUG, other]})

    assert isinstance(out["bugs"], Overwrite)
    assert out["bugs"].value == [other]


def test_a_group_of_bugs_alone_changes_nothing():
    node = make_final_merge_node(lambda lines: [[1, 2]])

    assert node({"differences": [FOUND], "bugs": [BUG, BUG]}) == {}


def test_the_final_merge_numbers_the_differences_first_then_the_bugs():
    seen = []

    def merge(lines):
        seen.append(dict(lines))
        return []

    make_final_merge_node(merge)({"differences": [FOUND], "bugs": [BUG]})

    assert seen == [{0: FOUND.text, 1: BUG.text}]


def test_with_one_list_empty_the_final_merge_asks_nothing():
    def never(lines):
        raise AssertionError("asked")

    node = make_final_merge_node(never)

    assert node({"differences": [], "bugs": [BUG]}) == {}
    assert node({"differences": [FOUND], "bugs": []}) == {}


def run(*, differences, bugs, merge=None, fits_value=False, saver=None):
    seen = []

    def make_prompt(chunks, **kwargs):
        seen.append(kwargs)
        return "the prompt", chunks

    graph = build_graph(
        measure=lambda a, b: {"A": "stored A", "B": "stored B"},
        fits=lambda sides, question, last_answer: fits_value,
        stuff=lambda sides, question: ((chunk(0),), None),
        search_one=lambda sides, query: (chunk(1),),
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: BOTH,
        make_prompt=make_prompt,
        generate=lambda prompt: "the result",
        extract_claims=lambda a: CLAIMS,
        find_differences=differences,
        find_bugs=bugs,
        final_merge=merge,
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "chat"}} if saver else None
    final = graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"}, config)
    return final, seen


def test_the_two_finders_run_at_the_same_time_and_respond_runs_once():
    barrier = threading.Barrier(2, timeout=5)

    def differences(a, b, facts):
        barrier.wait()
        return (FOUND,)

    def bugs(artifact, summary):
        barrier.wait()
        return (BUG,)

    _, seen = run(differences=differences, bugs=bugs)

    assert len(seen) == 1
    assert seen[0]["differences"] == [FOUND]
    assert seen[0]["bugs"] == [BUG]


def test_the_differences_get_the_facts_of_the_claims():
    facts = []

    def differences(a, b, given):
        facts.append(given)
        return ()

    run(differences=differences, bugs=lambda artifact, summary: ())

    assert facts == [("the batch is 128",)]


def test_the_final_merge_runs_between_the_finders_and_respond():
    _, seen = run(
        differences=lambda a, b, facts: (FOUND,),
        bugs=lambda artifact, summary: (BUG,),
        merge=lambda lines: [[0, 1]],
    )

    assert seen[0]["differences"] == [FOUND]
    assert not seen[0]["bugs"]


def test_on_the_stuffed_path_only_the_bugs_are_hunted():
    def differences(a, b, facts):
        raise AssertionError("the stuffed answer sees both files whole")

    _, seen = run(
        differences=differences, bugs=lambda artifact, summary: (BUG,), fits_value=True
    )

    assert seen[0]["bugs"] == [BUG]
    assert not seen[0]["differences"]


def test_the_findings_of_one_message_do_not_pile_up_in_the_next():
    saver = InMemorySaver()
    run(differences=lambda a, b, f: (FOUND,), bugs=lambda a, s: (BUG,), saver=saver)

    final, seen = run(
        differences=lambda a, b, f: (FOUND,), bugs=lambda a, s: (BUG,), saver=saver
    )

    assert seen[0]["differences"] == [FOUND]
    assert final["differences"] == [] and final["bugs"] == []
