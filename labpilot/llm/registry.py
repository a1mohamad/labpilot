from __future__ import annotations

from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
CLOUDFLARE_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
)

MISTRAL_REASONING: dict[str, object] = {"reasoning_effort": "high", "top_p": 1}
OPENROUTER_REASONING: dict[str, object] = {"reasoning": {"effort": "high"}}
OPENAI_REASONING: dict[str, object] = {"reasoning_effort": "high"}

GOOGLE_CONTEXT = 1_048_576
GOOGLE_OUTPUT = 65_536


def _gemini(
    *,
    name: str,
    tier: int,
    model: str,
    context_window: int = GOOGLE_CONTEXT,
    max_output_tokens: int = GOOGLE_OUTPUT,
    max_input_tokens: int | None = None,
) -> GeminiProvider:
    return GeminiProvider(
        name=name,
        tier=tier,
        url=GOOGLE_URL,
        model=model,
        api_key_env="GOOGLE_API_KEY",
        quota_pool=f"GOOGLE:{model}",
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        max_input_tokens=max_input_tokens,
        thinking="HIGH",
    )


GEMINI_3_7_FLASH = _gemini(name="Gemini 3.7 Flash", tier=1, model="gemini-3.7-flash")
GEMINI_3_6_FLASH = _gemini(name="Gemini 3.6 Flash", tier=2, model="gemini-3.6-flash")
GEMINI_3_5_FLASH = _gemini(name="Gemini 3.5 Flash", tier=3, model="gemini-3.5-flash")

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

NEMOTRON_3_ULTRA = OpenAICompatibleProvider(
    name="Nemotron 3 Ultra",
    tier=5,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=1_000_000,
    max_output_tokens=65_536,
    extra_body=OPENROUTER_REASONING,
)

GEMINI_3_5_FLASH_LITE = _gemini(
    name="Gemini 3.5 Flash-Lite", tier=6, model="gemini-3.5-flash-lite"
)

MISTRAL_MEDIUM = OpenAICompatibleProvider(
    name="Mistral Medium",
    tier=7,
    url=MISTRAL_URL,
    model="mistral-medium-latest",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=MISTRAL_REASONING,
)

GEMINI_3_1_FLASH_LITE = _gemini(
    name="Gemini 3.1 Flash-Lite", tier=8, model="gemini-3.1-flash-lite"
)

NEMOTRON_3_SUPER = OpenAICompatibleProvider(
    name="Nemotron 3 Super",
    tier=9,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-super-120b-a12b:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=OPENROUTER_REASONING,
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

MAGISTRAL_SMALL = OpenAICompatibleProvider(
    name="Magistral Small",
    tier=11,
    url=MISTRAL_URL,
    model="magistral-small-latest",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=262_144,
    extra_body=MISTRAL_REASONING,
)

NORTH_MINI_CODE = OpenAICompatibleProvider(
    name="North Mini Code",
    tier=12,
    url=OPENROUTER_URL,
    model="cohere/north-mini-code:free",
    api_key_env="OPENROUTER_API_KEY",
    context_window=256_000,
    max_output_tokens=64_000,
    extra_body=OPENROUTER_REASONING,
)

DEVSTRAL_2 = OpenAICompatibleProvider(
    name="Devstral 2",
    tier=13,
    url=MISTRAL_URL,
    model="devstral-2512",
    api_key_env="MISTRAL_API_KEY",
    context_window=262_144,
    max_output_tokens=16_384,
)

GEMMA_4_31B = _gemini(
    name="Gemma 4 31B",
    tier=14,
    model="gemma-4-31b-it",
    context_window=262_144,
    max_output_tokens=32_768,
    max_input_tokens=16_000,
)

GPT_OSS_120B_GROQ = OpenAICompatibleProvider(
    name="GPT-OSS 120B (Groq)",
    tier=15,
    url=GROQ_URL,
    model="openai/gpt-oss-120b",
    api_key_env="GROQ_API_KEY",
    context_window=131_072,
    max_output_tokens=65_536,
    max_input_tokens=8_000,
    extra_body=OPENAI_REASONING,
)

CHAIN = (
    GEMINI_3_7_FLASH,
    GEMINI_3_6_FLASH,
    GEMINI_3_5_FLASH,
    GLM_5_2,
    NEMOTRON_3_ULTRA,
    GEMINI_3_5_FLASH_LITE,
    MISTRAL_MEDIUM,
    GEMINI_3_1_FLASH_LITE,
    NEMOTRON_3_SUPER,
    GPT_OSS_120B,
    MAGISTRAL_SMALL,
    NORTH_MINI_CODE,
    DEVSTRAL_2,
    GEMMA_4_31B,
    GPT_OSS_120B_GROQ,
)
