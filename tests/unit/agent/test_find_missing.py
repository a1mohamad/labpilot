import logging
import threading

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from labpilot.agent import (
    A_SILENT,
    MAX_ITEMS_PER_ANSWER,
    Claim,
    CodeFinding,
    DifferencesError,
    Finding,
    Plan,
    Query,
    allowed_steps,
    build_graph,
    differences_schema,
    read_code_findings,
)
from labpilot.agent.find_missing import STEP, make_find_missing_node, wants_missing
from labpilot.agent.plan_check import STEPS_BY_FILES
from labpilot.ingest import Chunk

SOURCES = ["[train.py · def encode · lines 1-9]", "[train.py · def pool · lines 10-19]"]
TEXTS = ["mask = mask * stop_mask", "context = weights @ proj"]
BOTH = Plan(steps=("extract_claims", STEP), queries=(Query("B", "mask"),))
ONLY_SCAN = Plan(steps=(STEP,), queries=(Query("B", "mask"),))
NEITHER = Plan(steps=("summarize",), queries=(Query("B", "mask"),))


def item(text, part, quote, a_says="A does not say"):
    return {"text": text, "part": part, "quote": quote, "a_says": a_says}


def found(text="B masks stopwords"):
    return CodeFinding(text, SOURCES[0], "stop_mask", A_SILENT)


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


def claim(n):
    return Claim(f"fact {n}", "[paper.md]", f"quote {n}")


def test_the_schema_asks_for_a_text_a_part_a_quote_and_what_a_says():
    item_schema = differences_schema()["properties"]["items"]["items"]

    assert item_schema["required"] == ["text", "part", "quote", "a_says"]


def test_an_item_gets_its_place_from_its_part_number_and_keeps_a_words():
    arguments = {
        "items": [
            item("B pools projections", 1, "weights @ proj", "a sum of hidden states")
        ]
    }

    (got,) = read_code_findings(arguments, SOURCES, TEXTS)

    assert got == CodeFinding(
        "B pools projections", SOURCES[1], "weights @ proj", "a sum of hidden states"
    )


@pytest.mark.parametrize("a_says", ["", "   ", None, 3])
def test_an_empty_a_says_means_a_is_silent(a_says):
    arguments = {"items": [{**item("B masks", 0, "stop_mask"), "a_says": a_says}]}

    assert read_code_findings(arguments, SOURCES, TEXTS)[0].a_says == A_SILENT


def test_an_item_whose_quote_is_not_in_its_part_is_dropped(caplog):
    arguments = {
        "items": [item("made up", 0, "never written"), item("B masks", 0, "stop_mask")]
    }

    with caplog.at_level(logging.WARNING):
        got = read_code_findings(arguments, SOURCES, TEXTS)

    assert [g.text for g in got] == ["B masks"]
    assert "1 of 2 code findings dropped" in caplog.text


def test_the_part_that_shows_it_is_kept_when_the_parts_are_given():
    parts = [chunk(0), chunk(1)]
    arguments = {"items": [item("B pools", 1, "weights @ proj")]}

    assert read_code_findings(arguments, SOURCES, TEXTS, parts)[0].evidence is parts[1]


RUNAWAY = [item(f"x {n}", 0, "stop_mask") for n in range(MAX_ITEMS_PER_ANSWER + 1)]


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"items": "x"},
        {"items": [item("x", 5, "stop_mask")]},
        {"items": [item("  ", 0, "stop_mask")]},
        {"items": [item("x", 0, "nowhere")]},
        {"items": RUNAWAY},
    ],
)
def test_an_answer_that_is_not_a_good_list_is_refused(arguments):
    with pytest.raises(DifferencesError):
        read_code_findings(arguments, SOURCES, TEXTS)


def test_the_step_is_one_the_planner_may_choose_for_two_files_and_not_for_one():
    assert STEP in allowed_steps(("A", "B"))
    assert STEP not in allowed_steps(("B",))
    assert wants_missing({"plan": ONLY_SCAN})
    assert not wants_missing({"plan": NEITHER})


def test_the_node_reads_both_files():
    seen = []

    def find(a, b):
        seen.append((a, b))
        return (found(),)

    result = make_find_missing_node(find)({"a": "A-1", "b": "B-1"})

    assert result == {"code_findings": [found()]}
    assert seen == [("A-1", "B-1")]


def test_a_failed_scan_gives_no_findings_and_logs_why(caplog):
    def broken(a, b):
        raise DifferencesError("no tier")

    with caplog.at_level(logging.WARNING):
        result = make_find_missing_node(broken)({"a": "A-1", "b": "B-1"})

    assert result == {"code_findings": []}
    assert "no tier" in caplog.text


def run(plan, *, claims=(), find=None, check=None, fits_value=False, saver=None):
    seen = []

    def make_prompt(chunks, **kwargs):
        seen.append(kwargs)
        return "the prompt", chunks

    graph = build_graph(
        measure=lambda a, b: {"A": "stored A", "B": "stored B"},
        fits=lambda sides, question: fits_value,
        stuff=lambda sides, question: ((chunk(0),), None),
        search_one=lambda sides, query: (chunk(1),),
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: plan,
        make_prompt=make_prompt,
        generate=lambda prompt: "the result",
        extract_claims=lambda a: claims,
        check=check,
        find_missing=find,
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": "chat"}} if saver else None
    final = graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"}, config)
    return final, seen


def test_the_checks_and_the_scan_run_together_and_respond_runs_once():
    fits_value = False  # the checks and the scan run on the search path only
    barrier = threading.Barrier(2, timeout=5)

    def check(c, chunks):
        barrier.wait()
        return Finding(c, "match", "", "[s]", "", "same")

    def find(a, b):
        barrier.wait()
        return (found(),)

    _, seen = run(
        BOTH, claims=(claim(1),), find=find, check=check, fits_value=fits_value
    )

    assert len(seen) == 1
    assert seen[0]["code_findings"] == [found()]
    assert [f.claim for f in seen[0]["findings"]] == [claim(1)]


def test_the_scan_runs_alone_when_the_plan_has_no_claims():
    _, seen = run(ONLY_SCAN, find=lambda a, b: (found(),))

    assert seen[0]["code_findings"] == [found()]
    assert "findings" not in seen[0]


def test_the_scan_runs_when_the_claims_give_nothing_to_check():
    def check(c, chunks):
        raise AssertionError("no claim to check")

    _, seen = run(BOTH, claims=(), find=lambda a, b: (found(),), check=check)

    assert seen[0]["code_findings"] == [found()]


def test_a_plan_without_the_step_never_scans():
    def find(a, b):
        raise AssertionError("not planned")

    _, seen = run(NEITHER, find=find)

    assert "code_findings" not in seen[0]


def test_the_code_findings_of_one_message_do_not_pile_up_in_the_next():
    saver = InMemorySaver()
    run(ONLY_SCAN, find=lambda a, b: (found("first"),), saver=saver)
    final, seen = run(ONLY_SCAN, find=lambda a, b: (found("second"),), saver=saver)

    assert seen[0]["code_findings"] == [found("second")]
    assert final["code_findings"] == []


def test_every_step_the_planner_may_list_is_run_by_a_node():
    # R18: on 2026-10-24 the planner listed find_bugs and extract_outcomes on
    # every run, and no node ran them.
    graph = build_graph(
        measure=lambda a, b: None,
        fits=lambda s, q: True,
        stuff=lambda s, q: ((), None),
        search_one=lambda s, q: (),
        totals_of=lambda s: {},
        rank_side=lambda q, p: p,
        plan=lambda q, a, b: None,
        make_prompt=lambda c, **k: ("", c),
        generate=lambda p: "",
        summarize=lambda a: "",
        extract_claims=lambda a: (),
        check=lambda c, x: None,
        find_missing=lambda a, b: (),
    )
    nodes = set(graph.get_graph().nodes)
    run_by = {"summarize": {"summarize_a", "summarize_b"}}
    for steps in STEPS_BY_FILES.values():
        for step in steps:
            assert run_by.get(step, {step}) <= nodes, step


def test_when_everything_was_read_neither_the_checks_nor_the_scan_run():
    def check(c, chunks):
        raise AssertionError("no check on the stuffed path")

    def find(a, b):
        raise AssertionError("no scan on the stuffed path")

    _, seen = run(BOTH, claims=(claim(1),), find=find, check=check, fits_value=True)

    assert len(seen) == 1
    assert "findings" not in seen[0] and "code_findings" not in seen[0]
