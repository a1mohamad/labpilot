from __future__ import annotations

import logging
from collections.abc import Mapping

from labpilot.embed.contracts import Rate

logger = logging.getLogger(__name__)

# What a provider told us about ITSELF, keyed by model.
#
# The registry's numbers are SEEDS, because the first decision - which model to
# use - happens before any call, so no header can inform it. Google sends no
# rate header at all (measured 2026-09-13), so for Google the seed is the only
# source there will ever be.
_OBSERVED: dict[str, dict[str, int]] = {}

# Mistral spells them this way and sends only the request one on a 200:
# x-ratelimit-limit-req-minute: 60, measured 2026-09-13. The token limit
# appears on a 429. Google sends neither.
_HEADERS = {
    "requests_per_minute": "x-ratelimit-limit-req-minute",
    "tokens_per_minute": "x-ratelimit-limit-tokens-minute",
}

# Cloudflare reports what the call COST, not what is left. Logged and never
# acted on: a running total kept in memory resets on restart, so it would
# under-count spend and claim budget we do not have. A real spend tracker
# needs persistence, and that is not this piece.
_NEURONS = "cf-ai-neurons"


def learn(model: str, headers: Mapping[str, str], declared: Rate | None = None) -> None:
    """Record any limit the provider just told us, and CHECK it against ours.

    Letting observation override a seed silently would be worse than hardcoding
    it: a wrong constant would be quietly replaced and nobody would ever learn
    it was wrong. So a disagreement warns - the same job `_validated` does when
    a real vector's width contradicts the declared `dim`.
    """
    seen: dict[str, int] = {}
    for field, header in _HEADERS.items():
        raw = headers.get(header)
        if raw is None:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value <= 0:
            continue

        seen[field] = value
        stated = getattr(declared, field, None) if declared else None
        if stated is not None and stated != value:
            logger.warning(
                "%s reports %s = %d, the registry declares %d - the seed is stale",
                model,
                field,
                value,
                stated,
            )

        if seen:
            _OBSERVED.setdefault(model, {}).update(seen)

        cost = headers.get(_NEURONS)
        if cost is not None:
            logger.info("%s cost %s neurons", model, cost)


def observed(model: str) -> dict[str, int]:
    return _OBSERVED.get(model, {})


def forget() -> None:
    """Tests only - module state that leaks between tests is a shared fixture."""
    _OBSERVED.clear()
