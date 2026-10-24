import psycopg
import pytest

from labpilot.agent import CheckError, Query
from labpilot.api import asking
from labpilot.api.errors import ArtifactChanged, EmbeddingUnavailable
from labpilot.llm import CHAIN, GEMINI_3_5_FLASH_LITE, LLMClient


def capture(monkeypatch):
    monkeypatch.setattr(
        asking, "make_query_writer", lambda client: ("new_query", client)
    )
    seen = {}

    def fake_build_graph(**kwargs):
        seen.update(kwargs)
        return "the graph"

    monkeypatch.setattr(asking, "build_graph", fake_build_graph)
    monkeypatch.setattr(
        asking, "make_planner", lambda conn, client: ("planner", client)
    )
    monkeypatch.setattr(
        asking, "make_claims_extractor", lambda conn, client: ("extract", client)
    )
    monkeypatch.setattr(asking, "make_checker", lambda client: ("check", client))
    return seen


def test_the_graph_gets_the_function_that_makes_claims_and_the_one_that_checks(
    monkeypatch,
):
    seen = capture(monkeypatch)

    asking._ask_graph("conn", "client")

    assert seen["extract_claims"] == ("extract", "client")
    assert seen["check"] == ("check", "client")


def test_both_get_the_same_client_and_it_starts_with_flash_lite(monkeypatch):
    seen = capture(monkeypatch)
    client = LLMClient()

    asking._ask_graph("conn", client)

    claims_client = seen["extract_claims"][1]
    assert seen["check"][1] is claims_client
    assert claims_client.chain[0].model == GEMINI_3_5_FLASH_LITE.model
    assert len(claims_client.chain) == len(CHAIN)


def test_the_graph_gets_a_writer_of_new_queries_that_shares_the_same_client(
    monkeypatch,
):
    seen = capture(monkeypatch)
    client = LLMClient()

    asking._ask_graph("conn", client)

    claims_client = seen["extract_claims"][1]
    assert seen["new_query"][0] == "new_query"
    assert seen["new_query"][1] is claims_client
    assert claims_client is not client


def test_the_planner_and_the_client_the_caller_gave_keep_their_own_chain(monkeypatch):
    seen = capture(monkeypatch)
    client = LLMClient()

    asking._ask_graph("conn", client)

    assert seen["plan"][1] is client
    assert client.chain == CHAIN


FAULTS = [
    pytest.param(EmbeddingUnavailable("the embedder is down"), id="embedder-down"),
    pytest.param(ArtifactChanged("re-ingested"), id="re-ingested"),
    pytest.param(psycopg.OperationalError("SSL SYSCALL error: EOF"), id="database"),
]


@pytest.mark.parametrize("fault", FAULTS)
def test_a_failed_claim_search_is_a_check_error_and_the_question_search_is_not(
    monkeypatch, fault
):
    seen = capture(monkeypatch)

    def broken(*_args, **_kwargs):
        raise fault

    monkeypatch.setattr(asking, "retrieve_query", broken)
    asking._ask_graph("conn", "client")

    with pytest.raises(CheckError):
        seen["search_claim"]({}, Query("B", "a claim"))
    with pytest.raises(type(fault)):
        seen["search_one"]({}, Query("B", "the question"))


def test_a_bug_in_the_search_is_not_turned_into_an_unchecked_claim(monkeypatch):
    seen = capture(monkeypatch)

    def bug(*_args, **_kwargs):
        raise TypeError("a bug of ours")

    monkeypatch.setattr(asking, "retrieve_query", bug)
    asking._ask_graph("conn", "client")

    with pytest.raises(TypeError):
        seen["search_claim"]({}, Query("B", "a claim"))
