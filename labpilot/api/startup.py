from __future__ import annotations

import logging
import os

from labpilot.llm import CHAIN
from labpilot.llm.chain import Provider

logger = logging.getLogger(__name__)


def configured_providers(chain: tuple[Provider, ...] = CHAIN) -> tuple[str, ...]:
    return tuple(
        provider.name for provider in chain if os.environ.get(provider.api_key_env)
    )


def validate_provider_keys(chain: tuple[Provider, ...] = CHAIN) -> tuple[str, ...]:
    usable = configured_providers(chain)
    if not usable:
        raise RuntimeError(
            "no provider in the chain has its API key set, so every request "
            "would fail with AllFreeTiersExhausted. Copy .env.example to .env "
            f"and fill in at least one of: "
            f"{', '.join(sorted({one.api_key_env for one in chain}))}"
        )

    missing = sorted(
        {
            provider.api_key_env
            for provider in chain
            if not os.environ.get(provider.api_key_env)
        }
    )
    if missing:
        logger.warning(
            "starting with %d of %d tiers usable; no key for: %s",
            len(usable),
            len(chain),
            ", ".join(missing),
        )

    return usable
