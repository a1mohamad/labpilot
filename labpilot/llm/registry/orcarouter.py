"""The tiers of Orcarouter."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry._shared import _gateway

ORCAROUTER_URL = "https://api.orcarouter.ai/v1/chat/completions"


# Its own free-package page: 10 requests a minute, 50 a day, for the account.
ORCAROUTER_REQUESTS_PER_MINUTE = 10


def _orcarouter(**kwargs) -> OpenAICompatibleProvider:
    return _gateway(
        url=ORCAROUTER_URL,
        key="ORCAROUTER_API_KEY",
        requests_per_minute=ORCAROUTER_REQUESTS_PER_MINUTE,
        **kwargs,
    )


ORCAROUTER_GLM_5_3_FLASH = _orcarouter(
    name="GLM-5.3 Flash (OrcaRouter)",
    model="z-ai/glm-5.3-flash-free",
    context_window=1_310_720,
    max_output_tokens=131_072,
)


ORCAROUTER_DEEPSEEK_V4_FLASH = _orcarouter(
    name="DeepSeek V4 Flash (OrcaRouter)",
    model="deepseek/deepseek-v4-flash-free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


# OrcaRouter, same day. DeepSeek V4.1 Flash is the AA v4.3.2 = 39 model that
# LiteRouter also serves; this route answered in 2.3 s against 17 s there, but
# OrcaRouter allows 50 a day, so it goes AFTER the LiteRouter ids.
ORCAROUTER_DEEPSEEK_V4_1_FLASH = _orcarouter(
    name="DeepSeek V4.1 Flash (OrcaRouter)",
    model="deepseek/deepseek-v4.1-flash-free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


ORCAROUTER_HY3 = _orcarouter(
    name="Hy3 (OrcaRouter)",
    model="tencent/hy3-free",
    context_window=262_144,
    max_output_tokens=65_536,
)


# ADDED 2026-11-16 after 5 of 5 probes answered in 5.8 to 7.0 s (a reasoning model:
# 130 to 194 tokens for a one-sentence answer). OrcaRouter's catalogue and Kilo's
# list give no window and no output cap, so both are CONSERVATIVE GUESSES, not
# measurements: it serves small jobs until a long answer is tried.
ORCAROUTER_HY4_PREVIEW = _orcarouter(
    name="Hy4 preview (OrcaRouter)",
    model="tencent/hy4-preview-free",
    context_window=131_072,
    max_output_tokens=16_384,
)
