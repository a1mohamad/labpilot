from __future__ import annotations

from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


GEMINI_3_6_FLASH = GeminiProvider(
    name="Gemini 3.6 Flash",
    tier=2,
    url=GOOGLE_URL,
    model="gemini-3.6-flash",
    api_key_env="GOOGLE_API_KEY",
)

GLM_5_2 = OpenAICompatibleProvider(
    name="GLM-5.2",
    tier=2,
    url=MISTRAL_URL,
    model="glm-5-2",
    api_key_env="MISTRAL_API_KEY",
)


GEMINI_3_5_FLASH = GeminiProvider(
    name="Gemini 3.5 Flash",
    tier=3,
    url=GOOGLE_URL,
    model="gemini-3.5-flash",
    api_key_env="GOOGLE_API_KEY",
)

NEMOTRON_3_ULTRA = OpenAICompatibleProvider(
    name="Nemotron 3 Ultra",
    tier=1,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key_env="OPENROUTER_API_KEY",
)

NORTH_MINI_CODE = OpenAICompatibleProvider(
    name="North Mini Code",
    tier=4,
    url=OPENROUTER_URL,
    model="cohere/north-mini-code:free",
    api_key_env="OPENROUTER_API_KEY",
)

DEVSTRAL_2 = OpenAICompatibleProvider(
    name="Devstral 2",
    tier=6,
    url=MISTRAL_URL,
    model="devstral-2512",
    api_key_env="MISTRAL_API_KEY",
)

CHAIN = (
    GEMINI_3_6_FLASH,
    GLM_5_2,
    GEMINI_3_5_FLASH,
    NEMOTRON_3_ULTRA,
    NORTH_MINI_CODE,
    DEVSTRAL_2,
)
