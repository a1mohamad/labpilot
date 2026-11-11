import logging

import pytest

from labpilot.api.main import configure_logging


@pytest.fixture
def labpilot_logger():
    logger = logging.getLogger("labpilot")
    before = logger.level
    yield logger
    logger.setLevel(before)


def test_info_makes_the_labpilot_loggers_print_info(labpilot_logger):
    labpilot_logger.setLevel(logging.NOTSET)

    configure_logging("info")

    assert labpilot_logger.level == logging.INFO


@pytest.mark.parametrize("name", ["", "nonsense"])
def test_an_empty_or_unknown_level_leaves_the_server_quiet(labpilot_logger, name):
    labpilot_logger.setLevel(logging.NOTSET)

    configure_logging(name)

    assert labpilot_logger.level == logging.NOTSET
