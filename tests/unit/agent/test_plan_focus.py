"""What the planner's choices do (D105, D107): a question about one of two files
is answered from that file alone, and a question that needs no file is answered
as a chat. Fakes only: what is checked is the graph, not the database."""

from __future__ import annotations

from labpilot.agent import Plan, Query, build_graph
from labpilot.agent.plan_check import check_plan, focus
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


def plan_of(**fields) -> Plan:
    steps = fields.pop("steps", ("find_differences", "find_bugs"))
    queries = fields.pop("queries", (Query("A", "qa"), Query("B", "qb")))
    return Plan(steps=steps, queries=queries, **fields)


# ---- the plan is cut down in code -----------------------------------------


def test_a_question_about_b_drops_the_comparison_and_the_queries_of_a():
    cut = focus(plan_of(about="B"), BOTH)

    assert cut.steps == ("find_bugs",)
    assert cut.queries == (Query("B", "qb"),)


def test_a_question_about_a_also_drops_the_bug_hunt():
    cut = focus(plan_of(about="A"), BOTH)

    assert cut.steps == ()
    assert cut.queries == (Query("A", "qa"),)


def test_a_question_that_needs_no_file_runs_nothing_but_the_answer():
    cut = focus(plan_of(files=False), BOTH)

    assert (cut.steps, cut.queries) == ((), ())


def test_a_plan_about_both_is_left_alone():
    plan = plan_of()

    assert focus(plan, BOTH) == plan


def test_the_check_applies_the_focus_to_a_good_plan():
    checked = check_plan(plan_of(about="B"), "q", BOTH)

    assert "find_differences" not in checked.steps


# ---- the graph follows the plan ---------------------------------------------


def run(plan: Plan, *, gate_verdict: str | None = None, fits: bool = True):
    calls: list[str] = []
    seen: dict = {}

    def make_prompt(chunks, question, totals, summaries, files, last_answer, **rest):
        seen.update(files=files, chunks=chunks, totals=totals, rest=rest)
        return "the prompt", chunks

    def stuff(sides, question):
        calls.append("stuff")
        return (chunk("A", 1), chunk("B", 1)), None

    def search_one(sides, query):
        calls.append(f"search {query.side}")
        return (chunk(query.side, 7),)

    extra = {}
    if gate_verdict:
        from labpilot.agent import Correspondence

        extra = {
            "gate": lambda sa, sb: Correspondence(gate_verdict, "different things"),
            "halt_answer": lambda sa, sb, reason: "HALT",
        }
    graph = build_graph(
        measure=lambda a, b: {s: "stored" for s, i in (("A", a), ("B", b)) if i},
        fits=lambda sides, question, last_answer: fits,
        stuff=stuff,
        search_one=search_one,
        totals_of=lambda sides: {"A": 5, "B": 6},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: plan,
        make_prompt=make_prompt,
        generate=lambda prompt: "answer",
        summarize=lambda artifact_id: f"summary of {artifact_id}",
        **extra,
    )
    final = graph.invoke({"question": "q", "a": "A-1", "b": "B-1"})
    return final, calls, seen


def test_a_question_about_b_searches_only_b_and_answers_from_one_file():
    final, calls, seen = run(plan_of(about="B"), fits=False)

    assert sorted(calls) == ["search B", "search B"]
    assert seen["files"] == 1
    assert {c.side for c in seen["chunks"]} == {"B"}
    assert seen["totals"] == {"B": 6}


def test_a_question_about_a_is_answered_as_a_reference():
    _, _, seen = run(plan_of(about="A"), fits=False)

    assert seen["files"] == 1
    assert seen["rest"]["reference"] is True


def test_when_everything_is_read_the_other_file_is_left_out_of_the_prompt():
    _, _, seen = run(plan_of(about="B"), fits=True)

    assert {c.side for c in seen["chunks"]} == {"B"}


def test_a_question_that_needs_no_file_reads_and_searches_nothing():
    final, calls, seen = run(plan_of(files=False), fits=False)

    assert calls == []
    assert seen["files"] == 0
    assert seen["chunks"] == ()
    assert final["chunks"] == () and final["totals"] is None


def test_a_chat_question_is_never_halted_by_the_gate():
    final, _, seen = run(plan_of(files=False), gate_verdict="NONE")

    assert final["result"] == "answer"
    assert seen["files"] == 0


def test_a_question_about_one_file_is_never_halted_by_the_gate():
    final, _, _ = run(plan_of(about="B"), gate_verdict="NONE")

    assert final["result"] == "answer"


def test_a_question_about_both_is_still_halted_on_none():
    final, _, _ = run(plan_of(), gate_verdict="NONE")

    assert final["result"] == "HALT"


def test_a_chat_question_gets_none_of_the_findings():
    from labpilot.agent import Bug
    from labpilot.agent.respond import make_respond_node

    seen = {}

    def make_prompt(chunks, **kwargs):
        seen.update(kwargs, chunks=chunks)
        return "the prompt", chunks

    bug = Bug("code", "it breaks", "[f.py]", "x", evidence=chunk("B", 1))
    node = make_respond_node(make_prompt, lambda prompt: "answer")

    node(
        {
            "question": "q",
            "a": "A-1",
            "b": "B-1",
            "plan": plan_of(files=False),
            "bugs": (bug,),
            "chunks": (),
        }
    )

    assert seen["bugs"] == () and seen["evidence"] == ()
    assert seen["chunks"] == ()
