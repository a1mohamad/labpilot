"""A question the first analysis did not cover gets ONE new check (D107)."""

from __future__ import annotations

import pytest

from labpilot.agent import Difference, Plan, Query, build_graph
from labpilot.agent.errors import DifferencesError
from labpilot.agent.fresh import make_fresh_node, wants_fresh
from labpilot.agent.plan_check import focus
from labpilot.ingest import Chunk

BOTH = ("A", "B")


def chunk(side: str, index: int) -> Chunk:
    return Chunk(
        text=f"text {side}{index}",
        source="f.py",
        start_line=index,
        end_line=index + 1,
        side=side,
        artifact_id=f"{side}-1",
        chunk_index=index,
    )


FOUND = Difference("missing", "B never does it", "[f.py]", "x")


def plan_of(**fields) -> Plan:
    return Plan(steps=(), queries=(Query("B", "qb"),), **fields)


@pytest.mark.parametrize(
    ("plan", "b", "expected"),
    [
        (plan_of(fresh=True), "B-1", True),
        (plan_of(fresh=True, about="B"), "B-1", True),
        (plan_of(fresh=False), "B-1", False),
        (plan_of(fresh=True), "", False),
        (plan_of(fresh=True, about="A"), "B-1", False),
        (plan_of(fresh=True, files=False), "B-1", False),
    ],
)
def test_a_new_check_runs_only_for_a_fresh_question_about_a_file_b(plan, b, expected):
    assert wants_fresh({"plan": plan, "b": b}) is expected


def test_the_node_gives_the_findings_to_the_differences():
    node = make_fresh_node(lambda question, b: (FOUND,))

    assert node({"question": "q", "b": "B-1"}) == {"differences": [FOUND]}


def test_a_failed_check_gives_no_finding_and_the_answer_goes_on():
    def broken(question, b):
        raise DifferencesError("no tier answered")

    assert make_fresh_node(broken)({"question": "q", "b": "B-1"}) == {"differences": []}


def test_a_bug_in_the_check_is_not_hidden():
    def buggy(question, b):
        raise KeyError("bug")

    with pytest.raises(KeyError):
        make_fresh_node(buggy)({"question": "q", "b": "B-1"})


def test_focus_keeps_fresh_for_b_and_for_both_and_drops_it_elsewhere():
    assert focus(plan_of(fresh=True, about="B"), BOTH).fresh is True
    assert focus(plan_of(fresh=True), BOTH).fresh is True
    assert focus(plan_of(fresh=True, about="A"), BOTH).fresh is False
    assert focus(plan_of(fresh=True, files=False), BOTH).fresh is False


def run(plan: Plan, *, fits: bool, with_fresh: bool = True):
    calls: list[tuple[str, str]] = []
    seen: dict = {}

    def make_prompt(chunks, question, totals, summaries, files, last_answer, **rest):
        seen.update(rest)
        return "the prompt", chunks

    def fresh(question, b):
        calls.append((question, b))
        return (FOUND,)

    graph = build_graph(
        measure=lambda a, b: {s: "stored" for s, i in (("A", a), ("B", b)) if i},
        fits=lambda sides, question, last_answer: fits,
        stuff=lambda sides, question: ((chunk("B", 1),), None),
        search_one=lambda sides, query: (chunk(query.side, 7),),
        totals_of=lambda sides: {"A": 5, "B": 6},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: plan,
        make_prompt=make_prompt,
        generate=lambda prompt: "answer",
        summarize=lambda artifact_id: "summary",
        fresh=fresh if with_fresh else None,
    )
    final = graph.invoke({"question": "does it x?", "a": "A-1", "b": "B-1"})
    return final, calls, seen


@pytest.mark.parametrize("fits", [True, False])
def test_the_new_check_runs_on_both_paths_and_its_finding_reaches_the_answer(fits):
    _, calls, seen = run(plan_of(fresh=True), fits=fits)

    assert calls == [("does it x?", "B-1")]
    assert list(seen["differences"]) == [FOUND]


@pytest.mark.parametrize("fits", [True, False])
def test_a_question_that_is_not_fresh_runs_no_new_check(fits):
    _, calls, seen = run(plan_of(fresh=False), fits=fits)

    assert calls == []
    assert list(seen["differences"]) == []


def test_a_graph_built_without_the_check_just_answers():
    final, calls, _ = run(plan_of(fresh=True), fits=False, with_fresh=False)

    assert calls == [] and final["result"] == "answer"
