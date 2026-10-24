from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from labpilot.llm import GEMINI_3_1_FLASH_LITE, GEMINI_3_5_FLASH_LITE, Provider

# The claims work is many short calls, and Flash-Lite is the best at it and the
# fastest (the size test, section 23.6), on 500 requests a day for each account.
# This is only the first version of a chain for this work: slice 11 builds the
# real one, and a spreader that sends parallel calls to the room with space.
CLAIMS_FIRST = (GEMINI_3_5_FLASH_LITE.model, GEMINI_3_1_FLASH_LITE.model)


def lead_with(chain: Sequence[Provider], models: Sequence[str]) -> tuple[Provider, ...]:
    """The same tiers, with every tier of these models moved to the front.

    Nothing is added and nothing is lost, and the tiers that stay behind keep
    their order. A model that is not in the chain moves nothing.
    """
    lead = tuple(
        provider
        for model in models
        for provider in chain
        if getattr(provider, "model", None) == model
    )
    taken = {id(provider) for provider in lead}
    return lead + tuple(provider for provider in chain if id(provider) not in taken)


def for_claims(client: Any) -> Any:
    # A client with no chain is a stand-in (a test hands over a string), and it
    # is used as it is.
    chain = getattr(client, "chain", None)
    if chain is None:
        return client
    return replace(client, chain=lead_with(chain, CLAIMS_FIRST))
