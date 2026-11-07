import threading
import time

from labpilot.api.tool_calls import ask_tool, at_once
from labpilot.llm import AllFreeTiersExhausted, LLMResult, Tool

TOOL = Tool(name="give", description="d", parameters={"type": "object"})


class Wrong(Exception):
    pass


def read(arguments):
    if "n" not in arguments:
        raise Wrong("no n")
    return arguments["n"]


class Client:
    def __init__(self, arguments):
        self.arguments = arguments
        self.hooks = []

    def generate(self, prompt, *, max_tokens, tool, problem_with):
        self.hooks.append(problem_with)
        if isinstance(self.arguments, Exception):
            raise self.arguments
        return LLMResult(text="", model="m", tier=1, arguments=self.arguments)


def ask(client):
    return ask_tool(client, "p", tool=TOOL, max_tokens=10, read=read, errors=(Wrong,))


def test_the_answer_is_read_and_returned():
    assert ask(Client({"n": 3})) == 3


def test_the_chain_is_told_to_send_a_wrong_answer_on_to_the_next_tier():
    client = Client({"n": 3})
    ask(client)

    (problem,) = client.hooks
    assert problem(LLMResult(text="", model="m", tier=1, arguments={})) == "no n"
    assert problem(LLMResult(text="", model="m", tier=1, arguments=None))
    assert problem(LLMResult(text="", model="m", tier=1, arguments={"n": 1})) is None


def test_no_tier_no_arguments_or_a_wrong_answer_give_none():
    assert ask(Client(AllFreeTiersExhausted(()))) is None
    assert ask(Client(None)) is None
    assert ask(Client({"m": 1})) is None


def test_the_jobs_run_at_the_same_time_and_keep_their_order():
    barrier = threading.Barrier(3, timeout=5)

    def work(n):
        barrier.wait()
        time.sleep(0.01 * (3 - n))
        return n * 10

    assert at_once(work, [1, 2, 3]) == [10, 20, 30]


def test_no_job_gives_no_answer():
    assert at_once(lambda job: job, []) == []


def test_a_bug_in_the_reader_is_not_hidden_as_no_answer():
    import pytest

    def buggy(arguments):
        raise TypeError("a bug of ours")

    with pytest.raises(TypeError):
        ask_tool(
            Client({"n": 1}), "p", tool=TOOL, max_tokens=10, read=buggy, errors=(Wrong,)
        )
