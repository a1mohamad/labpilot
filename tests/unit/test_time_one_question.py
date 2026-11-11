"""The reading of the two clocks in scripts/time_one_question.py."""

import pytest

from scripts.time_one_question import (
    call_table,
    critical_path,
    render,
    summarize_run,
)


def step(name, start, end):
    return {
        "kind": "step",
        "name": name,
        "start": start,
        "end": end,
        "seconds": end - start,
    }


def call(step_name, tool, seconds, *, tier=1, failed=0):
    return {
        "kind": "call",
        "step": step_name,
        "tool": tool,
        "seconds": seconds,
        "tier": tier,
        "model": "m",
        "failed": failed,
        "end": 0.0,
    }


# The planner and both summaries start together; the gate waits for the
# summaries, not for the planner.
STEPS = [
    step("plan", 1000.0, 1005.0),
    step("summarize_a", 1000.0, 1020.0),
    step("summarize_b", 1000.0, 1008.0),
    step("gate", 1020.0, 1022.0),
    step("measure", 1022.0, 1023.0),
    step("respond", 1023.0, 1100.0),
    step("remember", 1100.0, 1100.5),
]


def test_the_chain_follows_the_slowest_step_of_each_group():
    names = [s["name"] for s in critical_path(STEPS)]

    assert names == ["summarize_a", "gate", "measure", "respond", "remember"]


def test_a_step_that_ran_beside_the_chain_is_not_on_it():
    names = [s["name"] for s in critical_path(STEPS)]

    assert "plan" not in names
    assert "summarize_b" not in names


def test_no_steps_give_no_chain():
    assert critical_path([]) == []


def test_calls_are_grouped_by_step_and_tool_and_the_slowest_group_is_first():
    rows = call_table(
        [
            call("find_bugs", "list_defects", 10.0, failed=2),
            call("find_bugs", "list_defects", 30.0, failed=1),
            call("find_bugs", "answer_checklist", 5.0, tier=None, failed=108),
            call("respond", "", 60.0),
        ]
    )

    assert [(r["step"], r["tool"]) for r in rows] == [
        ("respond", "text"),
        ("find_bugs", "list_defects"),
        ("find_bugs", "answer_checklist"),
    ]
    bugs = rows[1]
    assert (bugs["calls"], bugs["seconds"], bugs["longest"]) == (2, 40.0, 30.0)
    assert bugs["failed_tiers"] == 3
    assert rows[2]["no_answer"] == 1


def test_a_run_reports_the_gaps_before_and_after_the_graph():
    run = summarize_run(STEPS, started=998.0, ended=1103.0)

    assert run["wall"] == pytest.approx(105.0)
    assert run["before_graph"] == pytest.approx(2.0)
    assert run["after_graph"] == pytest.approx(2.5)
    offsets = {s["name"]: s["offset"] for s in run["steps"]}
    assert offsets["respond"] == pytest.approx(25.0)
    assert run["path_seconds"] == pytest.approx(20 + 2 + 1 + 77 + 0.5)


def test_the_printout_marks_the_steps_on_the_chain():
    run = summarize_run([*STEPS, call("respond", "", 76.0)], 998.0, 1103.0)

    text = render("first", run)

    assert "respond" in text
    marked = [line for line in text.splitlines() if line.rstrip().endswith("*")]
    assert len(marked) == 5
    assert not any("plan" in line for line in marked)
    assert "1 model calls" in text
