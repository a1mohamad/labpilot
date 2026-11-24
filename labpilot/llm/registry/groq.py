"""The tiers of Groq."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry._shared import OPENAI_REASONING

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


# The SAME model on Groq, and modelled at 8,000 like GPT-OSS is - because the
# binding limit is a per-minute budget covering prompt AND reserved output,
# not the 131,042 context Groq advertises. Read from its own headers:
# x-ratelimit-limit-requests 1000, x-ratelimit-limit-tokens 8000.
#
# So it can NEVER serve a report and _check_fits refuses it locally for free.
# It is here for Step 2's small code jobs, where 1,000 requests a day and a
# 0.6s round trip are worth more than a context it cannot fill.
QWEN_3_8_27B_GROQ = OpenAICompatibleProvider(
    name="Qwen3.8 27B (Groq)",
    tier=0,
    url=GROQ_URL,
    model="qwen/qwen3.8-27b",
    api_key_env="GROQ_API_KEY",
    context_window=8_000,
    max_output_tokens=8_000,
    extra_body=OPENAI_REASONING,
)


GPT_OSS_120B_GROQ = OpenAICompatibleProvider(
    name="GPT-OSS 120B (Groq)",
    tier=12,
    url=GROQ_URL,
    model="openai/gpt-oss-120b",
    api_key_env="GROQ_API_KEY",
    context_window=8_000,
    max_output_tokens=8_000,
    extra_body=OPENAI_REASONING,
)


# ADDED 2026-11-02, UNSCORED (no v4.3.2 page was found), 1.5 s live. The smaller
# GPT-OSS on the same Groq account: the same 8,000-token per-minute budget, so
# it can never serve a report and _check_fits turns one away for free. Small
# jobs only, like its sibling.
GPT_OSS_20B_GROQ = OpenAICompatibleProvider(
    name="GPT-OSS 20B (Groq)",
    tier=0,
    url=GROQ_URL,
    model="openai/gpt-oss-20b",
    api_key_env="GROQ_API_KEY",
    context_window=8_000,
    max_output_tokens=8_000,
    extra_body=OPENAI_REASONING,
)
