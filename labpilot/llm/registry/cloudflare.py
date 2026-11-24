"""The tiers of Cloudflare."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry._shared import OPENAI_REASONING

CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
)


GPT_OSS_120B = OpenAICompatibleProvider(
    name="GPT-OSS 120B",
    tier=11,
    url=CLOUDFLARE_URL,
    model="@cf/openai/gpt-oss-120b",
    api_key_env="CLOUDFLARE_API_KEY",
    account_env="CLOUDFLARE_ACCOUNT_ID",
    stream_usage=False,
    context_window=128_000,
    max_output_tokens=128_000,
    extra_body=OPENAI_REASONING,
)


# ADDED 2026-09-19, and the placement rests on TWO independent sources
# because one of them contradicted the blogs badly. See CLAUDE.md.
#
#                        AA v4.3   Code Arena     out tok/s
#   GLM-5.3 Flash          42      1607  (#17)       94.6
#   Gemini 3.7 Flash       39         -             288.3
#   DeepSeek V4 Flash      35      1580  (#22)      211.9
#   Gemini 3.6 Flash       34      1537  (#32)      182.5
#   Qwen3.8-27B            34      1593  (#18)       43.1
#   Gemini 3.5 Flash       33      1500  (#44)      207.8
#
# ⚠ EVERY OTHER AA NUMBER IN THIS FILE IS FROM AN OLDER INDEX VERSION and is
# NOT comparable with these. v4.3 scores Flash-Lite at 23, where the table
# above the chain still says 37.4. Only re-scored models may be compared.
# THE SAME MODEL ON TWO HOSTS TAKES TWO DIFFERENT WORDS, measured:
#
#   Cloudflare  "Unexpected reasoning effort high. Supported types are
#                xhigh (default), medium, and low."
#   Groq        "invalid Qwen3.8 reasoning_effort" for xhigh; `high` is fine.
#
# So neither host accepts the other's value, and a single shared constant
# would break one of them. This file already records that the same model on
# two hosts has different LIMITS; it also has different PARAMETER VOCABULARY.
#
# xhigh is Cloudflare's default AND the setting Artificial Analysis scored at
# 34, so the placement in CHAIN describes the configuration we actually send.
QWEN_CF_REASONING = {"reasoning_effort": "xhigh"}


# THE CODING SPECIALIST, and that is a measured claim rather than a vendor
# one. On general intelligence it TIES Gemini 3.6 Flash (34 = 34); on Code
# Arena it beats it by 56 Elo (1593 against 1537) and beats DeepSeek V4 Flash
# too (#18 against #22). AA also ranks it #1 of 142 open-weights models in the
# 4B-40B class. Step 2 should ROUTE code-writing sub-tasks here rather than
# walking the chain - the same rule this file already applies to Devstral.
#
# Cloudflare FIRST because it is the only one of the two that can serve a
# report: 262,144 context against Groq's binding 8,000 tokens per MINUTE.
# Measured cost: 244 neurons for a 4,860-token call, so ~41 such calls a day
# out of 10,000. Slow, though - 43.1 tok/s is the lowest of any tier here.
QWEN_3_8_27B = OpenAICompatibleProvider(
    name="Qwen3.8 27B",
    tier=0,
    url=CLOUDFLARE_URL,
    model="@cf/qwen/qwen3.8-27b",
    api_key_env="CLOUDFLARE_API_KEY",
    account_env="CLOUDFLARE_ACCOUNT_ID",
    stream_usage=False,
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=QWEN_CF_REASONING,
)
