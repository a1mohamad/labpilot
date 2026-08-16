from __future__ import annotations

from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
)

MISTRAL_REASONING: dict[str, object] = {"reasoning_effort": "high", "top_p": 1}
OPENROUTER_REASONING: dict[str, object] = {"reasoning": {"effort": "high"}}
OPENAI_REASONING: dict[str, object] = {"reasoning_effort": "high"}


GEMINI_3_7_FLASH = GeminiProvider(
    name="Gemini 3.7 Flash",
    tier=1,
    url=GOOGLE_URL,
    model="gemini-3.7-flash",
    api_key_env="GOOGLE_API_KEY",
    context_window=1_048_576,
    max_output_tokens=65_536,
    thinking="HIGH",
)

GEMINI_3_6_FLASH = GeminiProvider(
    name="Gemini 3.6 Flash",
    tier=2,
    url=GOOGLE_URL,
    model="gemini-3.6-flash",
    api_key_env="GOOGLE_API_KEY",
    context_window=1_048_576,
    max_output_tokens=65_536,
    thinking="HIGH",
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

GLM_5_2 = OpenAICompatibleProvider(
    name="GLM-5.2",
    tier=4,
    url=MISTRAL_URL,
    model="glm-5-2",
    api_key_env="MISTRAL_API_KEY",
    context_window=1_048_576,
    max_output_tokens=1_048_576,
    extra_body=MISTRAL_REASONING,
)

MISTRAL_MEDIUM = OpenAICompatibleProvider(
    name="Mistral Medium",
    tier=5,
    url=MISTRAL_URL,
    model="mistral-medium-latest",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=MISTRAL_REASONING,
)

NEMOTRON_3_ULTRA = OpenAICompatibleProvider(
    name="Nemotron 3 Ultra",
    tier=6,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=1_000_000,
    max_output_tokens=65_536,
    extra_body=OPENROUTER_REASONING,
)

MAGISTRAL_SMALL = OpenAICompatibleProvider(
    name="Magistral Small",
    tier=7,
    url=MISTRAL_URL,
    model="magistral-small-latest",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=MISTRAL_REASONING,
)

NORTH_MINI_CODE = OpenAICompatibleProvider(
    name="North Mini Code",
    tier=8,
    url=OPENROUTER_URL,
    model="cohere/north-mini-code:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=256_000,
    max_output_tokens=64_000,
    extra_body=OPENROUTER_REASONING,
)

DEVSTRAL_2 = OpenAICompatibleProvider(
    name="Devstral 2",
    tier=9,
    url=MISTRAL_URL,
    model="devstral-2512",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=16_384,
)

GPT_OSS_120B = OpenAICompatibleProvider(
    name="GPT-OSS 120B",
    tier=10,
    url=CLOUDFLARE_URL,
    model="@cf/openai/gpt-oss-120b",
    api_key_env="CLOUDFLARE_API_KEY",
    account_env="CLOUDFLARE_ACCOUNT_ID",
    context_window=128_000,
    max_output_tokens=128_000,
    extra_body=OPENAI_REASONING,
)

CHAIN = (
    GEMINI_3_7_FLASH,
    GEMINI_3_6_FLASH,
    GEMINI_3_5_FLASH,
    GLM_5_2,
    MISTRAL_MEDIUM,
    NEMOTRON_3_ULTRA,
    MAGISTRAL_SMALL,
    NORTH_MINI_CODE,
    DEVSTRAL_2,
    GPT_OSS_120B,
)
