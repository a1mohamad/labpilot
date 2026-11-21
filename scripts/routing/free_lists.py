"""Read each gateway's FREE list and compare it with the chain.

    python -m scripts.routing.free_lists

Calls no model: the model lists are metadata and cost no quota. For each gateway
it prints two lists:

    GONE   live tiers of the chain that the gateway no longer lists as free.
           Probe them (speed_check.py --only NAME); if they fail, move them to
           KNOWN_DEAD in labpilot/llm/registry.py.
    NEW    free ids that no tier of the chain uses. A new id is only a
           CANDIDATE: probe it, find its Artificial Analysis score, and add it
           only if it is worth it (a tier in registry.py and a family in
           write_ratings.py). Many free models are too weak to be worth a tier.

A dead tier that is free again shows in BACK. The report is also written to
artifacts/routing-bench/logs/free_lists_<date>.json.
Google, Mistral, Groq, Cloudflare and Cline publish no free list here; their
tiers are checked by speed_check.py only.
"""

from __future__ import annotations

import json
import os

import requests

from scripts.routing._common import LOGS, load_env, today

load_env()

from labpilot.llm import registry as R  # noqa: E402

CATALOGUES = {  # the same lists as tests/smoke/test_gateway_tiers_are_free.py
    "KILO_API_KEY": "https://api.kilo.ai/api/gateway/models",
    "REQUESTY_API_KEY": "https://router.requesty.ai/v1/models",
    "LITEROUTER_API_KEY": "https://api.literouter.com/v1/models",
    "ORCAROUTER_API_KEY": "https://api.orcarouter.ai/v1/models",
    "ROUTEWAY_API_KEY": "https://api.routeway.ai/v1/models",
    "BAZAARLINK_API_KEY": "https://api.bazaarlink.ai/v1/models",
    "TOKEN_HARBOR_API_KEY": "https://tokenharbor.ai/v1/models",
    "OPENROUTER_API_KEY": "https://openrouter.ai/api/v1/models",
}


def _prices(pricing: dict):
    for key, value in pricing.items():
        if key.endswith("_per_million"):
            continue
        if isinstance(value, dict):
            yield from _prices(value)
        elif key != "unit":
            yield value


def costs_nothing(model: dict) -> bool:
    """Free means EVERY price it states is zero, and it states at least one."""
    pricing = model.get("pricing")
    prices = (
        list(_prices(pricing))
        if isinstance(pricing, dict)
        else [model.get("input_price"), model.get("output_price")]
    )
    prices.append(model.get("model_cost"))
    known = [p for p in prices if p not in (None, "")]
    try:
        return bool(known) and all(float(p) == 0 for p in known)
    except (TypeError, ValueError):
        return False


def free_ids(url: str, key: str) -> set[str]:
    response = requests.get(
        url, headers={"Authorization": f"Bearer {key}"}, timeout=(10, 60)
    )
    response.raise_for_status()
    body = response.json()
    items = body.get("data", body if isinstance(body, list) else [])
    ids = {str(m.get("id")) for m in items if costs_nothing(m)}
    # LiteRouter marks its free ids with ":free"; its prices do not always say 0
    ids |= {str(m.get("id")) for m in items if str(m.get("id", "")).endswith(":free")}
    return ids


def main() -> None:
    report = {}
    for env, url in CATALOGUES.items():
        key = os.environ.get(env)
        if not key:
            print(f"\n{env}: not set, skipped")
            continue
        try:
            free = free_ids(url, key)
        except (requests.RequestException, ValueError) as exc:
            print(f"\n{env}: the list could not be read ({exc.__class__.__name__})")
            continue
        ours = [t for t in R.CHAIN if t.api_key_env == env]
        live = {t.model: t.name for t in ours if t.name not in R.KNOWN_DEAD}
        dead = {t.model: t.name for t in ours if t.name in R.KNOWN_DEAD}
        gone = sorted(name for model, name in live.items() if model not in free)
        back = sorted(name for model, name in dead.items() if model in free)
        new = sorted(free - set(live) - set(dead))
        report[env] = {"free": len(free), "gone": gone, "back": back, "new": new}
        print(f"\n{env}: {len(free)} free ids, {len(live)} live tiers")
        for label, names in (("GONE", gone), ("BACK", back), ("NEW", new)):
            if names:
                print(f"  {label}: " + ", ".join(names))
    out = LOGS / f"free_lists_{today()}.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
