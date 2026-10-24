import logging
import threading

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from labpilot.agent import (
    CheckError,
    Claim,
    Finding,
    Plan,
    Query,
    allowed_steps,
    build_graph,
)
from labpilot.agent.check_one import EVIDENCE_PARTS, make_check_node
from labpilot.agent.fan_out_claims import fan_out_claims
from labpilot.ingest import Chunk

SIDES = {"A": "stored A", "B": "stored B"}
WANTS = Plan(steps=("extract_claims",), queries=(Query("B", "time step"),))
NOT_WANTED = Plan(steps=("summarize",), queries=(Query("B", "time step"),))


def claim(number):
    return Claim(f"fact {number}", f"[paper.md · part {number}]", f"quote {number}")


def chunk(index):
    return Chunk(
        text=f"text {index}",
        source="solver.py",
        start_line=index,
        end_line=index,
        side="B",
        artifact_id="B-1",
        chunk_index=index,
    )


def finding_for(claim, verdict="match"):
    return Finding(claim, verdict, "", "[solver.py]", "dt = 0.01", "same step")


class Boom(Exception):
    pass


def test_the_step_is_searched_in_side_b_with_the_text_of_the_claim():
    seen = []

    def search_one(sides, query):
        seen.append((sides, query))
        return (chunk(0),)

    node = make_check_node(search_one, lambda c, chunks: finding_for(c))

    node({"sides": {"B": "stored B"}, "claim": claim(1)})

    assert seen == [({"B": "stored B"}, Query("B", "fact 1"))]


def test_only_the_first_parts_of_the_search_reach_the_check():
    given = []
    found = tuple(chunk(index) for index in range(EVIDENCE_PARTS + 4))

    def check(claim, chunks):
        given.append(chunks)
        return finding_for(claim)

    make_check_node(lambda sides, query: found, check)(
        {"sides": SIDES, "claim": claim(1)}
    )

    assert given == [found[:EVIDENCE_PARTS]]


def test_the_node_returns_the_finding_in_a_list_for_the_add_rule():
    node = make_check_node(lambda s, q: (chunk(0),), lambda c, chunks: finding_for(c))

    result = node({"sides": SIDES, "claim": claim(1)})

    assert result == {"findings": [finding_for(claim(1))]}


def test_when_nothing_is_found_the_claim_is_absent_and_no_check_is_paid_for():
    def check(claim, chunks):
        raise AssertionError("no model call for a claim with no evidence")

    result = make_check_node(lambda s, q: (), check)(
        {"sides": SIDES, "claim": claim(1)}
    )

    [finding] = result["findings"]
    assert (finding.claim, finding.verdict) == (claim(1), "absent")


def test_a_check_that_fails_leaves_an_unchecked_claim_and_logs_why(caplog):
    def check(claim, chunks):
        raise CheckError("no tier could check it (3)")

    node = make_check_node(lambda s, q: (chunk(0),), check)

    with caplog.at_level(logging.WARNING):
        result = node({"sides": SIDES, "claim": claim(1)})

    [finding] = result["findings"]
    assert (finding.claim, finding.verdict) == (claim(1), "unchecked")
    assert "no tier could check it" in caplog.text


def test_any_other_error_reaches_the_caller_unchanged():
    def check(claim, chunks):
        raise Boom("a bug")

    node = make_check_node(lambda s, q: (chunk(0),), check)

    with pytest.raises(Boom):
        node({"sides": SIDES, "claim": claim(1)})


def test_no_claims_means_straight_to_respond():
    assert fan_out_claims({"claims": (), "sides": SIDES}) == "respond"
    assert fan_out_claims({"sides": SIDES}) == "respond"


def test_each_claim_gets_its_own_send_with_only_side_b():
    sends = fan_out_claims({"claims": (claim(1), claim(2)), "sides": SIDES})

    assert [send.node for send in sends] == ["check_one", "check_one"]
    assert [send.arg["claim"] for send in sends] == [claim(1), claim(2)]
    assert all(send.arg["sides"] == {"B": "stored B"} for send in sends)


def run(
    claims,
    check,
    *,
    plan=WANTS,
    fits_value=True,
    saver=None,
    thread="chat-1",
    seen=None,
):
    seen = [] if seen is None else seen

    def make_prompt(chunks, **kwargs):
        seen.append(kwargs)
        return "the prompt", chunks

    graph = build_graph(
        measure=lambda a, b: SIDES,
        fits=lambda sides, question: fits_value,
        stuff=lambda sides, question: ((chunk(0),), None),
        search_one=lambda sides, query: (chunk(1),),
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: plan,
        make_prompt=make_prompt,
        generate=lambda prompt: "the result",
        extract_claims=lambda question, a: claims,
        check=check,
        checkpointer=saver,
    )
    config = {"configurable": {"thread_id": thread}} if saver else None
    final = graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"}, config)
    return final, seen


def by_text(findings):
    return sorted(findings, key=lambda finding: finding.claim.text)


@pytest.mark.parametrize("fits_value", [True, False])
def test_every_claim_is_checked_and_the_answer_gets_all_the_findings(fits_value):
    claims = (claim(1), claim(2), claim(3))

    _, seen = run(claims, lambda c, chunks: finding_for(c), fits_value=fits_value)

    assert len(seen) == 1
    assert [finding.claim for finding in by_text(seen[0]["findings"])] == list(claims)


def test_the_checks_run_at_the_same_time_and_not_one_after_the_other():
    barrier = threading.Barrier(2, timeout=2)

    def check(claim, chunks):
        barrier.wait()
        return finding_for(claim)

    _, seen = run((claim(1), claim(2)), check)

    assert len(seen[0]["findings"]) == 2


def test_with_no_claims_the_answer_is_asked_for_without_findings():
    final, seen = run((), lambda c, chunks: pytest.fail("nothing to check"))

    assert "findings" not in seen[0]
    assert final["result"] == "the result"


def test_a_claim_that_could_not_be_checked_still_reaches_the_answer():
    def check(claim, chunks):
        raise CheckError("every tier failed")

    final, seen = run((claim(1),), check)

    [finding] = seen[0]["findings"]
    assert (finding.claim, finding.verdict) == (claim(1), "unchecked")
    assert final["result"] == "the result"


def test_a_plan_without_the_step_never_checks():
    _, seen = run(
        (claim(1),), lambda c, chunks: pytest.fail("not wanted"), plan=NOT_WANTED
    )

    assert "findings" not in seen[0]


def test_without_a_check_function_there_is_no_check_step_and_the_run_goes_on():
    graph = build_graph(
        measure=lambda a, b: SIDES,
        fits=lambda sides, question: True,
        stuff=lambda sides, question: ((chunk(0),), None),
        search_one=lambda sides, query: (chunk(1),),
        totals_of=lambda sides: {"A": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: WANTS,
        make_prompt=lambda chunks, **_: ("the prompt", chunks),
        generate=lambda prompt: "the result",
        extract_claims=lambda question, a: (claim(1),),
    )

    final = graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"})

    assert "check_one" not in graph.get_graph().nodes
    assert final["result"] == "the result"


def test_the_step_is_only_offered_for_two_files():
    assert "extract_claims" in allowed_steps(("A", "B"))


def test_when_the_message_ends_the_claims_and_the_findings_are_cleared():
    final, _ = run((claim(1), claim(2)), lambda c, chunks: finding_for(c))

    assert final["claims"] == ()
    assert final["findings"] == []


def test_the_findings_of_one_message_do_not_pile_up_in_the_next_one():
    saver = InMemorySaver()
    first, second = [], []

    run(
        (claim(1), claim(2)),
        lambda c, chunks: finding_for(c),
        saver=saver,
        seen=first,
    )
    run((claim(3),), lambda c, chunks: finding_for(c), saver=saver, seen=second)

    assert len(first[0]["findings"]) == 2
    assert [finding.claim for finding in second[0]["findings"]] == [claim(3)]


def test_the_checks_search_with_the_function_made_for_them_when_one_is_given():
    searched = []

    def search_claim(sides, query):
        searched.append(query)
        return (chunk(1),)

    graph = build_graph(
        measure=lambda a, b: SIDES,
        fits=lambda sides, question: True,
        stuff=lambda sides, question: ((chunk(0),), None),
        search_one=lambda sides, query: pytest.fail("a claim must not use this one"),
        search_claim=search_claim,
        totals_of=lambda sides: {"A": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: WANTS,
        make_prompt=lambda chunks, **_: ("the prompt", chunks),
        generate=lambda prompt: "the result",
        extract_claims=lambda question, a: (claim(1),),
        check=lambda c, chunks: finding_for(c),
    )

    graph.invoke({"question": "why?", "a": "A-1", "b": "B-1"})

    assert searched == [Query("B", "fact 1")]
