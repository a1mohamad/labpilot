"""M3 — which tiers accept a `tools` field, and which actually call it.

    PYTHONPATH=. python scripts/probe_tools.py
    PYTHONPATH=. python scripts/probe_tools.py "Flash-Lite" "Gemma"

SPENDS ONE REQUEST PER TIER. Check the exit ISP first — see CLAUDE.md's
network precondition — because a refused exit looks exactly like a missing
capability in this table.

THE QUESTION. Step 2 needs the model to ask for things: a search, a rerank, a
file read. There are two channels, and which one we can use is a property of
the PROVIDER, not of our code:

    function calling   a `tools` field in, `tool_calls` out, provider-enforced
    structured output  JSON in the message body, parsed by us

Our chain falls back across 40 tiers, so a channel that only some of them
speak is a channel that breaks on the day tier 1 is spent. This measures how
many actually speak it.

THE PROMPT CANNOT BE ANSWERED WITHOUT THE TOOL. It asks for the weather in
Paris "right now" and says outright that the model cannot know it. A tier that
supports function calling has no honest way to answer except by calling.

THREE OUTCOMES, and the middle one is the dangerous one:

    CALLED    a real tool call, carrying the right argument
    IGNORED   HTTP 200, no tool call — the field was accepted and dropped
    REFUSED   non-200 — but read the body before believing it, because most
              refusals here are 503, 429 or a blocked exit rather than an
              answer about capability

IGNORED is why the production rule is DETECT, NEVER CONFIGURE: a per-tier
capability flag would record such a tier as working, and nothing would ever
correct it.
"""

from __future__ import annotations

import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.registry import CHAIN

PROMPT = (
    "What is the weather in Paris right now? "
    "You cannot know this. Use the get_weather tool."
)

OPENAI_TOOLS = [
    {
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
]

# The same tool, in Gemini's shape. Note the UPPERCASE types - the Gemini
# schema dialect is not JSON Schema, and lowercase "string" is refused.
GEMINI_TOOLS = [
    {
        "function_declarations": [
            {
                "name": "get_weather",
                "description": "Get the current weather in a city.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {"city": {"type": "STRING"}},
                    "required": ["city"],
                },
            }
        ]
    }
]

TIMEOUT = (10, 90)


def _gemini(provider: GeminiProvider) -> tuple[str, str, str]:
    reply = requests.post(
        f"{provider.url}/{provider.model}:generateContent",
        headers={
            "x-goog-api-key": os.environ.get(provider.api_key_env, ""),
            "Content-Type": "application/json",
        },
        json={
            "contents": [{"parts": [{"text": PROMPT}]}],
            "generationConfig": {"maxOutputTokens": 512, "temperature": 0.0},
            "tools": GEMINI_TOOLS,
        },
        timeout=TIMEOUT,
    )
    if reply.status_code != 200:
        return "REFUSED", f"HTTP {reply.status_code}", reply.text[:160]

    parts = (
        (reply.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    )
    for part in parts:
        if "functionCall" in part:
            return "CALLED", json.dumps(part["functionCall"])[:110], ""

    return (
        "IGNORED",
        "200, no functionCall",
        "".join(part.get("text", "") for part in parts)[:110],
    )


def _openai(provider: object) -> tuple[str, str, str]:
    url = provider.url
    if getattr(provider, "account_env", None):
        url = url.format(account_id=os.environ.get(provider.account_env, ""))

    reply = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {os.environ.get(provider.api_key_env, '')}",
            "Content-Type": "application/json",
        },
        json={
            "model": provider.model,
            "messages": [{"role": "user", "content": PROMPT}],
            "max_tokens": 512,
            "temperature": 0.0,
            "tools": OPENAI_TOOLS,
        },
        timeout=TIMEOUT,
    )
    if reply.status_code != 200:
        return "REFUSED", f"HTTP {reply.status_code}", reply.text[:160]

    body = reply.json()
    if isinstance(body.get("data"), dict):  # Cline wraps its reply
        body = body["data"]
    message = (body.get("choices") or [{}])[0].get("message") or {}
    if calls := message.get("tool_calls"):
        return "CALLED", json.dumps(calls[0])[:110], ""

    return "IGNORED", "200, no tool_calls", str(message.get("content"))[:110]


def main() -> None:
    load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))
    wanted = sys.argv[1:]

    for provider in CHAIN:
        if wanted and not any(word.lower() in provider.name.lower() for word in wanted):
            continue
        if not os.environ.get(provider.api_key_env, "").strip():
            print(f"{provider.name:32} SKIP     no key")
            continue

        started = time.time()
        try:
            probe = _gemini if isinstance(provider, GeminiProvider) else _openai
            verdict, detail, extra = probe(provider)
        except requests.RequestException as exc:
            verdict, detail, extra = "ERROR", type(exc).__name__, str(exc)[:110]

        print(f"{provider.name:32} {verdict:8} {time.time() - started:5.1f}s  {detail}")
        if extra:
            print(f"{'':42}{extra}")


if __name__ == "__main__":
    main()
