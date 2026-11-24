from dataclasses import replace
from typing import Any

from labpilot.llm import routes


def for_task(client: Any, task: str) -> Any:
    """Return a client configured for this task's route."""
    chain = getattr(client, "chain", None)
    if chain is None:
        return client

    walk = routes.resolve(task, chain)
    found = routes.ROUTES[task]
    return replace(
        client,
        chain=walk or chain,
        call_stop=found.stop,
        hedge_after=found.hedge,
        total_budget=found.budget,
    )
