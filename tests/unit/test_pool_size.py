from labpilot.agent import MAX_QUERIES
from labpilot.store import POOL_SIZE

SIDES = 2


def test_the_pool_has_one_connection_for_every_search_that_can_run_at_once():
    # the planner's queries plus the question on each side: raising the cap
    # without the pool puts the extra searches back in a queue
    assert POOL_SIZE == MAX_QUERIES + SIDES
