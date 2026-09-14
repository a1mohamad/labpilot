import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-smoke",
        action="store_true",
        default=False,
        help="run tests that call real providers and spend API quota",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-smoke"):
        return

    skip_smoke = pytest.mark.skip(reason="need --run-smoke (spends real API quota)")
    for item in items:
        if "smoke" in item.keywords:
            item.add_marker(skip_smoke)


@pytest.fixture(autouse=True)
def no_live_rerankers(request, monkeypatch):
    """Keep the rerank chain EMPTY for every test that is not a smoke test.

    MEASURED 2026-09-14, and it was live: any test that reached the search
    branch of the ask path went straight through to real providers. Nothing
    stubs the reranker, because _best takes its chain as a DEFAULT ARGUMENT
    captured at import time, so monkeypatching the module attribute does not
    reach it. One integration test was quietly spending four Gemini rerank
    calls and then Cohere on every full run - and Cohere's free tier is 1,000
    calls a MONTH, shared with chat and embed, for the rerank primary.

    An empty chain is not a mock: rerank() walks it, finds nothing, and ends
    in skip(), which is the real degraded path this project already ships.
    So the default behaviour under test is "no reranker was available", and a
    test that wants reranking has to say so and supply its own.
    """
    if "smoke" in request.keywords:
        return

    monkeypatch.setattr("labpilot.api.reranking.CHAIN", ())
