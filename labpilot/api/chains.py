from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from labpilot.llm import (
    GEMINI_3_1_FLASH_LITE,
    GEMINI_3_5_FLASH_LITE,
    KNOWN_DEAD,
    Provider,
)

# The claims work is many short calls, and Flash-Lite is the best at it and the
# fastest (the size test, section 23.6), on 500 requests a day for each account.
# This is only the first version of a chain for this work: slice 11 builds the
# real one, and a spreader that sends parallel calls to the room with space.
CLAIMS_FIRST = (GEMINI_3_5_FLASH_LITE.model, GEMINI_3_1_FLASH_LITE.model)
# The trace question of find_bugs: many calls on small groups. Measured on
# 2026-11-02 (section 29.8) against 4 other mid-level models: Flash-Lite 3.1
# together with the strong whole-file calls found as much as a strong trace,
# in 7 to 61 seconds a case.
TRACE_FIRST = (GEMINI_3_1_FLASH_LITE.model,)
# The skeptic of find_bugs: a few calls that must judge well. Flash-Lite let 9
# of 14 false suspects through as "real" (2026-11-02), so a stronger free model
# leads, on two routes (LiteRouter, OrcaRouter), and the Flash-Lite tiers
# follow.
SKEPTIC_FIRST = (
    "glm-5.3-flash:free",
    "z-ai/glm-5.3-flash-free",
    GEMINI_3_5_FLASH_LITE.model,
    GEMINI_3_1_FLASH_LITE.model,
)


def lead_with(chain: Sequence[Provider], models: Sequence[str]) -> tuple[Provider, ...]:
    """The same tiers, with every live tier of these models moved to the front.

    Nothing is added and nothing is lost, and the tiers that stay behind keep
    their order. A model that is not in the chain moves nothing, and a tier in
    KNOWN_DEAD stays at the tail (on 2026-11-03 the Cline route of GLM-5.3 began
    to answer 402, and it shares the model id with nothing live).
    """
    lead = tuple(
        provider
        for model in models
        for provider in chain
        if getattr(provider, "model", None) == model
        and getattr(provider, "name", None) not in KNOWN_DEAD
    )
    taken = {id(provider) for provider in lead}
    return lead + tuple(provider for provider in chain if id(provider) not in taken)


def _led(client: Any, models: Sequence[str]) -> Any:
    # A client with no chain is a stand-in (a test hands over a string), and it
    # is used as it is.
    chain = getattr(client, "chain", None)
    if chain is None:
        return client
    return replace(client, chain=lead_with(chain, models))


def for_claims(client: Any) -> Any:
    return _led(client, CLAIMS_FIRST)


def for_trace(client: Any) -> Any:
    return _led(client, TRACE_FIRST)


def for_skeptic(client: Any) -> Any:
    return _led(client, SKEPTIC_FIRST)


def bounded(client: Any, *, read: float, budget: float, retries: int = 1) -> Any:
    """The same chain, with a read time for every tier and a time for the call.

    A slow tier then costs at most `read` seconds and the whole call at most
    `budget`, so one hanging provider cannot use up the answer (D102).
    """
    chain = getattr(client, "chain", None)
    if chain is None:
        return client
    limited = tuple(
        replace(tier, timeout=(10.0, read)) if hasattr(tier, "timeout") else tier
        for tier in chain
    )
    return replace(
        client, chain=limited, total_budget=budget, max_retries_per_tier=retries
    )
