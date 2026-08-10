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
