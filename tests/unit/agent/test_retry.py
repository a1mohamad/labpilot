import logging

import pytest

from labpilot.agent import CheckError, Claim, Finding, Plan, Query, build_graph
from labpilot.agent.check_one import make_check_node
from labpilot.ingest import Chunk

SIDES = {"A": "stored A", "B": "stored B"}
WANTS = Plan(steps=("extract_claims",), queries=(Query("B", "time step"),))


def claim(number=1):
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


def verdict(claim, kind, note="a note"):
    return Finding(claim, kind, "", "[solver.py]", "dt = 0.01", note)


class Boom(Exception):
    pass


class Searches:
    """A search that answers by the text of the query, and remembers every one."""

    def __init__(self, answers):
        self.answers = answers
        self.queries = []

    def __call__(self, sides, query):
        self.queries.append(query)
        return self.answers.get(query.text, ())


class Checks:
    """A check that says what it is told for each part it is given."""

    def __init__(self, by_index):
        self.by_index = by_index
        self.calls = []

    def __call__(self, claim, chunks):
        self.calls.append(chunks)
        return verdict(claim, self.by_index[chunks[0].chunk_index])


class Writer:
    def __init__(self, *queries):
        self.queries = list(queries)
        self.calls = []

    def __call__(self, claim, tried, note):
        self.calls.append((claim, tried, note))
        return self.queries.pop(0) if self.queries else "another query"


def node(search, check, writer=None):
    return make_check_node(search, check, writer)


def run(node_, number=1):
    return node_({"sides": SIDES, "claim": claim(number)})["findings"]


def test_a_claim_that_is_absent_is_searched_again_with_the_new_query():
    search = Searches({"fact 1": (chunk(0),), "dt step": (chunk(1),)})
    check = Checks({0: "absent", 1: "match"})
    writer = Writer("dt step")

    [finding] = run(node(search, check, writer))

    assert finding.verdict == "match"
    assert [(q.side, q.text) for q in search.queries] == [
        ("B", "fact 1"),
        ("B", "dt step"),
    ]
    assert [chunks[0].chunk_index for chunks in check.calls] == [0, 1]


def test_the_writer_gets_the_claim_the_queries_so_far_and_what_the_check_said():
    search = Searches({"fact 1": (chunk(0),), "dt step": (chunk(1),)})
    writer = Writer("dt step")

    def check(claim, chunks):
        if chunks[0].chunk_index == 0:
            return verdict(claim, "absent", "the parts are about the output")
        return verdict(claim, "match")

    run(node(search, check, writer))

    assert writer.calls == [(claim(), ("fact 1",), "the parts are about the output")]


def test_a_claim_that_is_never_found_is_searched_three_times_and_stays_absent():
    search = Searches(
        {"fact 1": (chunk(0),), "q two": (chunk(0),), "q three": (chunk(0),)}
    )
    check = Checks({0: "absent"})
    writer = Writer("q two", "q three", "q four")

    [finding] = run(node(search, check, writer))

    assert finding.verdict == "absent"
    assert [q.text for q in search.queries] == ["fact 1", "q two", "q three"]
    assert len(check.calls) == 3
    assert len(writer.calls) == 2


def test_the_second_new_query_is_told_about_the_first_one():
    search = Searches({})
    writer = Writer("q two", "q three")

    run(node(search, Checks({}), writer))

    assert writer.calls[1][1] == ("fact 1", "q two")


@pytest.mark.parametrize("kind", ["match", "mismatch"])
def test_a_claim_that_is_found_on_the_first_search_is_never_searched_again(kind):
    search = Searches({"fact 1": (chunk(0),)})
    writer = Writer("never used")

    [finding] = run(node(search, Checks({0: kind}), writer))

    assert finding.verdict == kind
    assert len(search.queries) == 1
    assert writer.calls == []


def test_a_check_that_could_not_run_is_not_searched_again(caplog):
    def broken(claim, chunks):
        raise CheckError("no tier could check it (3)")

    writer = Writer("never used")

    with caplog.at_level(logging.WARNING):
        [finding] = run(node(Searches({"fact 1": (chunk(0),)}), broken, writer))

    assert finding.verdict == "unchecked"
    assert writer.calls == []
    assert "no tier could check it" in caplog.text


def test_when_the_second_check_fails_the_first_absent_stays():
    def check(claim, chunks):
        if chunks[0].chunk_index == 1:
            raise CheckError("no tier could check it (3)")
        return verdict(claim, "absent", "not in these parts")

    search = Searches({"fact 1": (chunk(0),), "dt step": (chunk(1),)})

    [finding] = run(node(search, check, Writer("dt step")))

    assert (finding.verdict, finding.note) == ("absent", "not in these parts")
    assert len(search.queries) == 2


def test_when_no_new_query_can_be_written_the_claim_stays_absent():
    search = Searches({"fact 1": (chunk(0),)})

    def writer(claim, tried, note):
        return None

    [finding] = run(node(search, Checks({0: "absent"}), writer))

    assert finding.verdict == "absent"
    assert len(search.queries) == 1


def test_a_search_that_finds_nothing_is_absent_without_a_check_and_is_tried_again():
    check = Checks({1: "match"})
    search = Searches({"dt step": (chunk(1),)})

    [finding] = run(node(search, check, Writer("dt step")))

    assert finding.verdict == "match"
    assert [chunks[0].chunk_index for chunks in check.calls] == [1]


def test_with_no_writer_there_is_one_search_and_nothing_else():
    search = Searches({"fact 1": (chunk(0),)})

    [finding] = run(node(search, Checks({0: "absent"})))

    assert finding.verdict == "absent"
    assert len(search.queries) == 1


def test_any_other_error_from_the_writer_reaches_the_caller_unchanged():
    def writer(claim, tried, note):
        raise Boom("a bug")

    with pytest.raises(Boom):
        run(node(Searches({"fact 1": (chunk(0),)}), Checks({0: "absent"}), writer))


def test_a_claim_that_was_searched_again_says_so_in_the_log(caplog):
    search = Searches({"fact 1": (chunk(0),), "dt step": (chunk(1),)})

    with caplog.at_level(logging.INFO):
        run(node(search, Checks({0: "absent", 1: "match"}), Writer("dt step")))

    assert "searched 2 times" in caplog.text
    assert "dt step" in caplog.text


def graph(search, check, writer):
    seen = []

    def make_prompt(chunks, **kwargs):
        seen.append(kwargs)
        return "the prompt", chunks

    built = build_graph(
        measure=lambda a, b: SIDES,
        fits=lambda sides, question: True,
        stuff=lambda sides, question: ((chunk(9),), None),
        search_one=search,
        totals_of=lambda sides: {"A": 1, "B": 1},
        rank_side=lambda question, pile: pile,
        plan=lambda question, a, b: WANTS,
        make_prompt=make_prompt,
        generate=lambda prompt: "the result",
        extract_claims=lambda question, a: (claim(1), claim(2)),
        check=check,
        new_query=writer,
    )
    built.invoke({"question": "why?", "a": "A-1", "b": "B-1"})
    return seen


def test_in_the_graph_every_claim_is_retried_and_the_answer_reads_the_final_ones():
    search = Searches(
        {
            "fact 1": (chunk(0),),
            "fact 2": (chunk(0),),
            "dt step": (chunk(1),),
        }
    )
    check = Checks({0: "absent", 1: "match"})

    seen = graph(search, check, Writer("dt step", "dt step"))

    [kwargs] = seen
    found = sorted(kwargs["findings"], key=lambda finding: finding.claim.text)
    assert [(f.claim.text, f.verdict) for f in found] == [
        ("fact 1", "match"),
        ("fact 2", "match"),
    ]
