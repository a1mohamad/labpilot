"""Routeway's free models - do they answer, how big a prompt do they take, and
do they call tools.

    PYTHONPATH=. python scripts/probe_routeway.py                # everything
    PYTHONPATH=. python scripts/probe_routeway.py ping           # one stage
    PYTHONPATH=. python scripts/probe_routeway.py ping deepseek  # one stage, one model

SPENDS REQUESTS: Routeway allows 5 a minute and 200 a day, and the minute
budget is the one that binds - the script paces itself to stay under it. Check
the exit ISP first (CLAUDE.md, network precondition): a refused exit looks like
a dead model.

WHAT IT MEASURES, AND WHY EACH STAGE EXISTS

    ping      3 calls per model. A single call is a sample of one, and this
              file has been wrong three times by reading one as a verdict
    context   growing prompts up to and past the DECLARED context_length. The
              catalogue says deepseek-v4-flash:free holds 42,000 tokens while
              the model itself holds 1,000,000, so the free route is capped
              and the cap is the number that decides where a tier may sit
    output    a huge max_tokens on a tiny prompt: refused, or clamped
    tools     one call with a tools field - CALLED, IGNORED or REFUSED

TWO TRAPS IT WORKS AROUND

    Routeway sends `x-cache-status` and `x-cache-ttl: 3600`, so it caches
    identical requests. Every prompt here carries a unique nonce, or a cache HIT
    would report a latency and a success that never touched a model.

    The real prompt size is read from `usage.prompt_tokens`, never from our own
    chars/3 estimate, which over-counts these tokenizers by about 1.66x.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

import requests
from dotenv import load_dotenv

URL = "https://api.routeway.ai/v1/chat/completions"
MODELS_URL = "https://api.routeway.ai/v1/models"
TIMEOUT = (10, 60)

# 5 requests a minute is the binding limit. 13s between calls keeps us under it.
PACE_SECONDS = 13.0

_last_call = 0.0


def _nonce() -> str:
    return uuid.uuid4().hex[:10]


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('ROUTEWAY_API_KEY', '')}",
        "Content-Type": "application/json",
    }


def _free_models() -> list[dict]:
    reply = requests.get(MODELS_URL, headers=_headers(), timeout=30)
    reply.raise_for_status()
    rows = reply.json().get("data", [])
    return [row for row in rows if row.get("id", "").endswith(":free")]


def _post(payload: dict) -> tuple[int, dict, dict, float, str]:
    """One paced request. Returns status, body, headers, seconds, error."""
    global _last_call
    wait = PACE_SECONDS - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)

    started = time.time()
    try:
        reply = requests.post(URL, headers=_headers(), json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        _last_call = time.time()
        return 0, {}, {}, time.time() - started, type(exc).__name__
    _last_call = time.time()

    try:
        body = reply.json()
    except ValueError:
        body = {"_raw": reply.text[:200]}
    return reply.status_code, body, dict(reply.headers), time.time() - started, ""


def _message(body: dict) -> dict:
    return ((body.get("choices") or [{}])[0].get("message")) or {}


def _quota(headers: dict) -> str:
    lowered = {key.lower(): value for key, value in headers.items()}
    return (
        f"min {lowered.get('x-ratelimit-remaining-minute', '?')}"
        f"/{lowered.get('x-ratelimit-limit-minute', '?')}  "
        f"day {lowered.get('x-ratelimit-remaining-day', '?')}"
        f"/{lowered.get('x-ratelimit-limit-day', '?')}  "
        f"cache {lowered.get('x-cache-status', '-')}"
    )


def _detail(status: int, body: dict, error: str) -> str:
    if error:
        return error
    if status != 200:
        raw = json.dumps(body, ensure_ascii=False)
        return raw[:170]
    message = _message(body)
    usage = body.get("usage") or {}
    reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    text = (message.get("content") or "").strip().replace("\n", " ")[:40]
    return (
        f"finish={(body.get('choices') or [{}])[0].get('finish_reason')}  "
        f"in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}"
        f"{f' think={reasoning}' if reasoning is not None else ''}  {text!r}"
    )


# ---- stage 1: ping ---------------------------------------------------------


# A REAL question, not "reply with one word". Measured 2026-09-29: on that
# prompt deepseek-v4-flash:free looped (`ok.ok.ok. responseok.`, finish=length)
# or hung past 120s, and on this one it answered correctly in 6-8s. A one-word
# prompt is a test of the prompt, not of the model - and HTTP 200 with a loop in
# the body is not an answer, so the check reads finish_reason and the text.
PING_QUESTION = (
    "In one sentence: what is wrong with "
    "`def f(xs, k): return [sum(xs[i-k:i+1])/k for i in range(len(xs))]`?"
)


def _whole_answer(status: int, body: dict) -> bool:
    """200 AND stopped on its own AND has text AND did not leak its thinking."""
    if status != 200:
        return False
    choice = (body.get("choices") or [{}])[0]
    text = (_message(body).get("content") or "").strip()
    stopped = choice.get("finish_reason") == "stop"
    return stopped and bool(text) and "<think>" not in text


def ping(model: dict, rounds: int = 3) -> None:
    ok = 0
    for i in range(rounds):
        payload = {
            "model": model["id"],
            "messages": [{"role": "user", "content": f"[{_nonce()}] {PING_QUESTION}"}],
            "max_tokens": 1024,
            "temperature": 0.0,
        }
        status, body, headers, seconds, error = _post(payload)
        ok += _whole_answer(status, body)
        print(
            f"  ping {i + 1}  {status or 'ERR':>3}  {seconds:5.1f}s  "
            f"{_detail(status, body, error)}"
        )
        print(f"{'':14}{_quota(headers)}")
    print(f"  -> {ok} of {rounds} WHOLE answers")


# ---- stage 2: context ------------------------------------------------------

# Real, code-shaped filler. Repeated verbatim text would be cached and would also
# tokenize better than real source, so each block carries its own number.
_BLOCK = (
    "def step_{i}(values, scale):\n"
    "    total = 0\n"
    "    for j, value in enumerate(values):\n"
    "        total += value * scale + j  # accumulate block {i}\n"
    "    return total\n\n"
)


def _filler(target_tokens: int) -> str:
    # About 40 real tokens per block; the real count is read back from usage.
    blocks = max(1, target_tokens // 40)
    return "".join(_BLOCK.format(i=i) for i in range(blocks))


def context(model: dict, sizes: list[int]) -> None:
    for target in sizes:
        payload = {
            "model": model["id"],
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"[{_nonce()}] Below is source code. Ignore it and reply "
                        f"with one word: ok\n\n{_filler(target)}"
                    ),
                }
            ],
            "max_tokens": 64,
            "temperature": 0.0,
        }
        status, body, headers, seconds, error = _post(payload)
        print(
            f"  ctx ~{target:>7,}  {status or 'ERR':>3}  {seconds:5.1f}s  "
            f"{_detail(status, body, error)}"
        )
        if status == 429:
            print(f"{'':14}{_quota(headers)}")
        if status not in (0, 200):
            print("  -> refused; larger sizes skipped")
            return


# ---- stage 3: output cap ---------------------------------------------------


def output(model: dict) -> None:
    for requested in (32_000, 131_072):
        payload = {
            "model": model["id"],
            "messages": [
                {"role": "user", "content": f"[{_nonce()}] Reply with one word: ok"}
            ],
            "max_tokens": requested,
            "temperature": 0.0,
        }
        status, body, _, seconds, error = _post(payload)
        print(
            f"  max_tokens {requested:>7,}  {status or 'ERR':>3}  {seconds:5.1f}s  "
            f"{_detail(status, body, error)}"
        )


# ---- stage 4: tools --------------------------------------------------------

TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather in a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


def tools(model: dict) -> None:
    payload = {
        "model": model["id"],
        "messages": [
            {
                "role": "user",
                "content": (
                    f"[{_nonce()}] What is the weather in Paris right now? "
                    "You cannot know this. Use the get_weather tool."
                ),
            }
        ],
        "max_tokens": 1024,
        "temperature": 0.0,
        "tools": [TOOL],
    }
    status, body, _, seconds, error = _post(payload)
    if status != 200:
        print(f"  tools  REFUSED  {status or 'ERR'}  {_detail(status, body, error)}")
        return
    message = _message(body)
    if calls := message.get("tool_calls"):
        print(f"  tools  CALLED   {seconds:5.1f}s  {json.dumps(calls[0])[:110]}")
    else:
        text = str(message.get("content"))[:80]
        print(f"  tools  IGNORED  {seconds:5.1f}s  200, no tool_calls  {text!r}")


STAGES = {"ping", "context", "output", "tools"}


def _sizes(declared: int) -> list[int]:
    """Real prompt sizes to try: a report prompt, then up to and past the cap."""
    steps = [16_000, int(declared * 0.7), int(declared * 0.95), int(declared * 1.1)]
    return sorted({step for step in steps if step >= 2_000})


def main() -> None:
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))
    words = [word.lower() for word in sys.argv[1:]]
    stages = [word for word in words if word in STAGES] or sorted(STAGES)
    wanted = [word for word in words if word not in STAGES]

    for model in _free_models():
        if wanted and not any(word in model["id"].lower() for word in wanted):
            continue
        declared = model.get("context_length") or 0
        print(f"\n== {model['id']}   declared context {declared:,}")
        if "ping" in stages:
            ping(model)
        if "context" in stages:
            context(model, _sizes(declared))
        if "output" in stages:
            output(model)
        if "tools" in stages:
            tools(model)


if __name__ == "__main__":
    main()
