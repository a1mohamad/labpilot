"""Availability, speed and trust of every live tier (the test of section 31.19).

    python -m scripts.routing.speed_check --quick            one short call each
    python -m scripts.routing.speed_check                    five calls each
    python -m scripts.routing.speed_check --only "DeepSeek" --providers literouter
    python -m scripts.routing.speed_check --dry-run          print the plan only

SPENDS REAL QUOTA. --quick is about 80 calls (one per live tier, a Google model on
each key); the full test is about five calls per model. The Gemini models that
allow 20 calls a day (3.6 Flash, 3.8 Flash, 4 Hydrogen) always get the quick
test only, and so do the second and third Google keys.

Every call sends a real code prompt with two random codes, one at the start and
one at the end, and asks the model to repeat them (so a cut prompt shows, and a
cache cannot answer). Sizes: 100, 200, 500, 4,000 and 20,000 tokens. A call is
VALID when the answer is not empty, ended by itself, and has no <think> text.
A failed call is asked again after 1 s and 3 s (the product rule); 400, 403 and
404 are not asked again. Two failed sizes end the test of a model. A call that
does not end in --stop seconds is a hang.

One JSON line per call goes to artifacts/routing-bench/logs/speed_<date>.jsonl.
write_ratings.py reads those logs. Providers run at the same time, one call at a
time inside each, paced by the provider's own limits.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import random
import string
import threading
import time

from scripts.routing._common import LOGS, REPO, append, check_network, load_env, today

load_env()

from labpilot.llm import registry as R  # noqa: E402
from labpilot.llm.errors import LLMError  # noqa: E402

SIZES = [("100", 100), ("200", 200), ("500", 500), ("4k", 4_000), ("long", 20_000)]
SCARCE = ("gemini-3.6-flash", "gemini-3.8-flash", "gemini-4-hydrogen")
LONG_FOR = {"gemma": 13_000, "GROQ": 6_000, "CLOUDFLARE": 8_000, "BAZAARLINK": 8_000}
SOURCE = "".join(
    p.read_text(encoding="utf-8") for p in sorted((REPO / "labpilot").rglob("*.py"))
)


def _code() -> str:
    return "ACCESS-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )


def _prompt(tokens: int) -> tuple[str, str, str]:
    a, b = _code(), _code()
    body = SOURCE[random.randint(0, 50_000) :][: int(tokens * 3.9)]
    text = (
        f"Code A is {a}.\n{body}\nCode B is {b}.\nReply with one line: A=<code A>; "
        "B=<code B>; then one sentence about what the code above does."
    )
    return text, a, b


def _lane(tier) -> str:
    """One provider account; Google and Mistral limit each (key, model) room."""
    if tier.api_key_env.startswith(("GOOGLE", "MISTRAL")):
        return tier.quota_pool
    return tier.api_key_env


def _gap(tier) -> float:
    if tier.api_key_env.startswith("LITEROUTER"):
        return 9.5  # one call at a time, 8 s between messages (31.19)
    if tier.api_key_env.startswith("BAZAARLINK"):
        return 20.0  # a burst gets the account blocked for minutes
    rpm = getattr(tier, "requests_per_minute", None)
    return 60.0 / rpm + 0.5 if rpm else 1.0


def _long_size(tier) -> int:
    if "gemma" in getattr(tier, "model", "") and tier.api_key_env.startswith("GOOGLE"):
        return LONG_FOR["gemma"]
    for start, size in LONG_FOR.items():
        if tier.api_key_env.startswith(start):
            return size
    return 20_000


def _call(tier, prompt: str, stop: float):
    pool = cf.ThreadPoolExecutor(1)
    try:
        return pool.submit(tier.complete, prompt, max_tokens=4096).result(timeout=stop)
    finally:
        pool.shutdown(wait=False)  # a hung call is left behind, never waited for


def one_size(tier, label: str, tokens: int, log, stop: float) -> bool:
    prompt, a, b = _prompt(tokens)
    for attempt, wait in enumerate((0, 1, 3), start=1):
        time.sleep(wait)
        start = time.monotonic()
        result, error = None, None
        try:
            result = _call(tier, prompt, stop)
        except cf.TimeoutError:
            error = "hang"
        except LLMError as exc:
            error = str(exc)[:200]
        seconds = round(time.monotonic() - start, 2)
        valid = bool(
            result is not None
            and result.text.strip()
            and str(result.finish_reason).lower() in ("stop", "end_turn")
            and "<think>" not in result.text
        )
        append(
            log,
            {
                "name": tier.name,
                "model": tier.model,
                "length": label,
                "attempt": attempt,
                "seconds": seconds,
                "valid": valid,
                "needle": bool(result and a in result.text and b in result.text),
                "finish": result.finish_reason if result else None,
                "error": error,
                "text": result.text[:160] if result else None,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
        why = str(error or (result and result.finish_reason))[:60]
        verdict = "OK" if valid else f"FAIL {why}"
        print(f"{tier.name:44s} {label:5s} {seconds:7.1f}s {verdict}", flush=True)
        if valid:
            return True
        if error and any(
            code in error for code in ("HTTP 400", "HTTP 403", "HTTP 404")
        ):
            return False
    return False


def measure(tier, *, quick: bool, log, stop: float) -> int:
    sizes = SIZES[:1] if quick else SIZES
    good = failed = 0
    for label, tokens in sizes:
        tokens = _long_size(tier) if label == "long" else tokens
        if one_size(tier, label, tokens, log, stop):
            good += 1
        else:
            failed += 1
        if failed >= 2:
            break
        time.sleep(_gap(tier))
    return good


def chosen(args) -> list:
    live = [t for t in R.CHAIN if t.name not in R.KNOWN_DEAD]
    if args.only:
        live = [t for t in live if any(o.lower() in t.name.lower() for o in args.only)]
    if args.providers:
        live = [
            t
            for t in live
            if any(t.api_key_env.lower().startswith(p.lower()) for p in args.providers)
        ]
    return live


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="one short call per tier")
    ap.add_argument("--only", nargs="*", help="tier names that contain one of these")
    ap.add_argument(
        "--providers", nargs="*", help="key name starts, e.g. literouter groq"
    )
    ap.add_argument("--stop", type=float, default=300.0, help="seconds before a hang")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-network-check", action="store_true")
    args = ap.parse_args()

    tiers = chosen(args)
    lanes: dict[str, list] = {}
    for tier in tiers:
        lanes.setdefault(_lane(tier), []).append(tier)

    def is_quick(tier) -> bool:
        return (
            args.quick
            or getattr(tier, "model", "") in SCARCE
            or tier.name.endswith(("(key 2)", "(key 3)"))
        )

    full = sum(not is_quick(t) for t in tiers)
    print(
        f"{len(tiers)} tiers in {len(lanes)} lanes: {full} full tests, "
        f"{len(tiers) - full} quick ones"
    )
    if args.dry_run:
        for lane, members in lanes.items():
            print(f"  {lane}: " + ", ".join(t.name for t in members))
        return
    if not args.no_network_check:
        check_network()
    log = LOGS / f"speed_{today()}.jsonl"
    lock = threading.Lock()
    summary: dict[str, int] = {}

    def run(members):
        for tier in members:
            good = measure(tier, quick=is_quick(tier), log=log, stop=args.stop)
            with lock:
                summary[tier.name] = good
            time.sleep(_gap(tier))

    threads = [
        threading.Thread(target=run, args=(m,), daemon=True) for m in lanes.values()
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    dead = sorted(name for name, good in summary.items() if good == 0)
    print(f"\nlog: {log}")
    print(f"answered at least once: {len(summary) - len(dead)} of {len(summary)}")
    if dead:
        print(
            "NO valid answer (check them before moving any to KNOWN_DEAD):",
            *dead,
            sep="\n  ",
        )


if __name__ == "__main__":
    main()
