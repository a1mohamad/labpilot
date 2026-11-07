import re
import threading
from itertools import count

import pytest

from labpilot.agent import (
    AUDIT_TOOL_NAME,
    JUDGE_TOOL_NAME,
    MERGE_TOOL_NAME,
    SCAN_TOOL_NAME,
    DifferencesError,
)
from labpilot.api import difference_finder as finder
from labpilot.api import file_parts
from labpilot.api.difference_review import make_merger
from labpilot.llm import AllFreeTiersExhausted, LLMResult
from labpilot.store import StoredChunk


def part(index, text, header, source):
    return StoredChunk(
        chunk_index=index,
        text=text,
        header=header,
        source=source,
        start_line=index + 1,
        end_line=index + 1,
    )


A = [part(0, "The batch is 128.", "[paper.md · 3]", "paper.md")]
B = [
    part(0, "batch = 64", "[train.py · part 0]", "train.py"),
    part(1, "seed = 7", "[train.py · part 1]", "train.py"),
]
FACTS = ["the batch is 128"]


class Client:
    """Answers each tool by its name, with a function of the prompt."""

    def __init__(self, **answers):
        self.answers = {
            AUDIT_TOOL_NAME: lambda prompt: {"answers": [same()]},
            SCAN_TOOL_NAME: lambda prompt: {"items": []},
            JUDGE_TOOL_NAME: judge("real", "differs"),
            MERGE_TOOL_NAME: lambda prompt: {"groups": []},
            **answers,
        }
        self.prompts = {}
        self.lock = threading.Lock()

    def generate(self, prompt, *, max_tokens, tool, problem_with=None):
        with self.lock:
            self.prompts.setdefault(tool.name, []).append(prompt)
        answer = self.answers[tool.name](prompt)
        if isinstance(answer, Exception):
            raise answer
        return LLMResult(text="", model="fake", tier=1, arguments=answer)


def same(n=0):
    return {"n": n, "verdict": "same"}


def breaks(n=0, quote="batch = 64"):
    return {"n": n, "verdict": "differs", "part": 0, "quote": quote, "why": "B uses 64"}


def judge(verdict, relation):
    def answer(prompt):
        listed = prompt.split("FINDINGS", 1)[1]
        numbers = [int(n) for n in re.findall(r"^(\d+)\. ", listed, re.M)]
        return {
            "answers": [
                {"n": n, "verdict": verdict, "relation": relation} for n in numbers
            ]
        }

    return answer


@pytest.fixture(autouse=True)
def stored(monkeypatch):
    monkeypatch.setattr(
        file_parts,
        "read_chunks",
        lambda conn, artifact_id: A if artifact_id[0] == "A" else B,
    )


def find(client, facts=FACTS, merge=None):
    run = finder.make_find_differences(
        "conn", whole=client, small=client, merge=merge or make_merger(client)
    )
    return run("A-1", "B-1", facts)


def test_a_fact_b_breaks_comes_back_placed_in_b_with_its_part():
    (found,) = find(Client(**{AUDIT_TOOL_NAME: lambda p: {"answers": [breaks()]}}))

    assert (found.kind, found.fact, found.quote) == ("differs", FACTS[0], "batch = 64")
    assert found.source == "[train.py · part 0]"
    assert found.evidence.chunk_index == 0


def test_one_vote_is_enough_to_flag_a_fact():
    calls = count()

    def audit(prompt):
        return {"answers": [breaks() if next(calls) == 0 else same()]}

    assert len(find(Client(**{AUDIT_TOOL_NAME: audit}))) == 1


def test_the_audit_asks_each_fact_twice_and_the_scan_sees_a_whole():
    client = Client()

    find(client)

    assert len(client.prompts[AUDIT_TOOL_NAME]) == 2
    (scan,) = client.prompts[SCAN_TOOL_NAME]
    assert "The batch is 128." in scan and "batch = 64" in scan


def test_a_big_a_is_shown_to_the_scan_as_its_facts(monkeypatch):
    monkeypatch.setattr(finder, "SCAN_A_TEXT_TOKENS", 0)
    client = Client()

    find(client)

    (scan,) = client.prompts[SCAN_TOOL_NAME]
    assert "the batch is 128" in scan and "The batch is 128." not in scan


def test_a_big_a_with_no_facts_cannot_be_compared(monkeypatch):
    monkeypatch.setattr(finder, "SCAN_A_TEXT_TOKENS", 0)

    with pytest.raises(DifferencesError, match="too big"):
        find(Client(), facts=[])


def test_with_no_facts_only_the_scan_runs():
    client = Client()

    find(client, facts=[])

    assert AUDIT_TOOL_NAME not in client.prompts
    assert SCAN_TOOL_NAME in client.prompts


def test_a_scan_item_the_judges_call_a_difference_from_a_is_differs():
    item = {"part": 1, "quote": "seed = 7", "what": "B fixes the seed", "why": ""}
    client = Client(**{SCAN_TOOL_NAME: lambda p: {"items": [item]}})

    (found,) = find(client)

    assert (found.kind, found.found_by) == ("differs", "scan")
    assert found.evidence.chunk_index == 1


@pytest.mark.parametrize("verdict", ["false", "minor"])
def test_a_finding_no_judge_calls_real_is_not_shown(verdict):
    client = Client(
        **{
            AUDIT_TOOL_NAME: lambda p: {"answers": [breaks()]},
            JUDGE_TOOL_NAME: judge(verdict, "differs"),
        }
    )

    assert find(client) == ()


def test_two_findings_of_one_point_are_shown_once():
    item = {"part": 0, "quote": "batch = 64", "what": "B uses 64", "why": ""}
    client = Client(
        **{
            AUDIT_TOOL_NAME: lambda p: {"answers": [breaks()]},
            SCAN_TOOL_NAME: lambda p: {"items": [item]},
            MERGE_TOOL_NAME: lambda p: {"groups": [[0, 1]]},
        }
    )

    (found,) = find(client)

    assert found.found_by == "audit"


def test_when_neither_the_audit_nor_the_scan_answers_the_error_says_so():
    def none(prompt):
        return AllFreeTiersExhausted(())

    client = Client(**{AUDIT_TOOL_NAME: none, SCAN_TOOL_NAME: none})

    with pytest.raises(DifferencesError, match="no tier"):
        find(client)


def test_the_merge_tries_the_next_client_and_with_no_answer_hides_nothing():
    def none(prompt):
        return AllFreeTiersExhausted(())

    good = Client(**{MERGE_TOOL_NAME: lambda p: {"groups": [[1, 2]]}})
    bad = Client(**{MERGE_TOOL_NAME: none})
    lines = {1: "x", 2: "y"}

    assert make_merger(bad, good)(lines) == [[1, 2]]
    assert make_merger(bad)(lines) == []
    assert make_merger(good)({1: "alone"}) == []
