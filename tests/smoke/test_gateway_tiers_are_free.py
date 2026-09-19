"""Every gateway tier must still be FREE on that gateway's own catalogue.

WHY THIS EXISTS
===============
`z-ai/glm-5.3-flash` was added as a Kilo tier on 2026-09-19 by matching
Cline's tier-1 MODEL ID against Kilo's catalogue. That is the wrong list. The
catalogue is what a gateway SERVES; the free list is what it serves for
NOTHING. Kilo charges $0.150/$0.500 per M for it, so the tier answered

    "Paid Model - Credits Required"

on every call - a dead tier burning a request per report, and invisible
because the chain swallows the failure and falls through to the next one.

It is a SMOKE test because it needs the live catalogue, and because the real
risk is not the mistake made once. It is a gateway QUIETLY MOVING a model
from free to paid. Cline's free roster changed twice in six days; Kilo's and
Requesty's will move too, and a snapshot committed today would be stale by
the time it mattered.

It spends no generation quota - both endpoints are metadata.
"""

from __future__ import annotations

import os

import pytest
import requests
from dotenv import load_dotenv

from labpilot.llm import CHAIN

load_dotenv()

CATALOGUES = {
    "KILO_API_KEY": "https://api.kilo.ai/api/gateway/models",
    "REQUESTY_API_KEY": "https://router.requesty.ai/v1/models",
}


def _free_ids(url: str, key: str) -> set[str]:
    response = requests.get(
        url, headers={"Authorization": f"Bearer {key}"}, timeout=(10, 60)
    )
    response.raise_for_status()
    body = response.json()
    items = body.get("data", body if isinstance(body, list) else [])

    free = set()
    for model in items:
        pricing = model.get("pricing")
        if isinstance(pricing, dict):
            prices = (pricing.get("prompt"), pricing.get("completion"))
        else:
            prices = (model.get("input_price"), model.get("output_price"))
        known = [p for p in prices if p is not None]
        try:
            if known and all(float(p) == 0 for p in known):
                free.add(str(model.get("id")))
        except (TypeError, ValueError):
            continue
    return free


@pytest.mark.smoke
@pytest.mark.parametrize("env_var,url", sorted(CATALOGUES.items()))
def test_every_gateway_tier_is_still_free_on_its_gateway(env_var: str, url: str):
    key = os.environ.get(env_var)
    if not key:
        pytest.skip(f"{env_var} is not set")

    ours = [provider for provider in CHAIN if provider.api_key_env == env_var]
    assert ours, f"no CHAIN tier uses {env_var}; delete this case or the key"

    free = _free_ids(url, key)
    assert free, f"{url} returned no zero-priced models at all - parse broken?"

    charged = [p.name for p in ours if p.model not in free]
    assert not charged, (
        f"{charged} are in CHAIN on {env_var} but are NOT free on that "
        f"gateway any more. A paid tier with no credits answers 'Credits "
        f"Required' on every call, and the chain swallows it - so it costs a "
        f"request per report while looking like nothing is wrong."
    )
