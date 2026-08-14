from __future__ import annotations

from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
)

MISTRAL_REASONING: dict[str, object] = {"reasoning_effort": "high"}
OPENROUTER_REASONING: dict[str, object] = {"reasoning": {"effort": "high"}}
OPENAI_REASONING: dict[str, object] = {"reasoning_effort": "high"}


GEMINI_3_6_FLASH = GeminiProvider(
    name="Gemini 3.6 Flash",
    tier=1,
    url=GOOGLE_URL,
    model="gemini-3.6-flash",
    api_key_env="GOOGLE_API_KEY",
    context_window=1_048_576,
    max_output_tokens=65_536,
    thinking="HIGH",
)

GLM_5_2 = OpenAICompatibleProvider(
    name="GLM-5.2",
    tier=2,
    url=MISTRAL_URL,
    model="glm-5-2",
    api_key_env="MISTRAL_API_KEY",
    context_window=1_048_576,
    max_output_tokens=1_048_576,
    extra_body=MISTRAL_REASONING,
)


GEMINI_3_5_FLASH = GeminiProvider(
    name="Gemini 3.5 Flash",
    tier=3,
    url=GOOGLE_URL,
    model="gemini-3.5-flash",
    api_key_env="GOOGLE_API_KEY",
    context_window=1_048_576,
    max_output_tokens=65_536,
    thinking="HIGH",
)

NEMOTRON_3_ULTRA = OpenAICompatibleProvider(
    name="Nemotron 3 Ultra",
    tier=4,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=1_000_000,
    max_output_tokens=65_536,
    extra_body=OPENROUTER_REASONING,
)

DEVSTRAL_2 = OpenAICompatibleProvider(
    name="Devstral 2",
    tier=5,
    url=MISTRAL_URL,
    model="devstral-2512",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=16_384,
    extra_body=MISTRAL_REASONING,
)

NORTH_MINI_CODE = OpenAICompatibleProvider(
    name="North Mini Code",
    tier=6,
    url=OPENROUTER_URL,
    model="cohere/north-mini-code:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=256_000,
    max_output_tokens=64_000,
    extra_body=OPENROUTER_REASONING,
)

GPT_OSS_120B = OpenAICompatibleProvider(
    name="GPT-OSS 120B",
    tier=7,
    url=CLOUDFLARE_URL,
    model="@cf/openai/gpt-oss-120b",
    api_key_env="CLOUDFLARE_API_KEY",
    account_env="CLOUDFLARE_ACCOUNT_ID",
    context_window=128_000,
    max_output_tokens=128_000,
    extra_body=OPENAI_REASONING,
)

CHAIN = (
    GEMINI_3_6_FLASH,
    GLM_5_2,
    GEMINI_3_5_FLASH,
    NEMOTRON_3_ULTRA,
    DEVSTRAL_2,
    NORTH_MINI_CODE,
    GPT_OSS_120B,
)
