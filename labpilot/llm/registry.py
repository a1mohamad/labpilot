from __future__ import annotations

from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

NEMOTRON_3_ULTRA = OpenAICompatibleProvider(
    name="Nemotron 3 Ultra",
    tier=1,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key_env="OPENROUTER_API_KEY",
)

GEMINI_3_6_FLASH = GeminiProvider(
    name="Gemini 3.6 Flash",
    tier=2,
    url=GOOGLE_URL,
    model="gemini-3.6-flash",
    api_key_env="GOOGLE_API_KEY",
)

GEMINI_3_5_FLASH = GeminiProvider(
    name="Gemini 3.5 Flash",
    tier=3,
    url=GOOGLE_URL,
    model="gemini-3.5-flash",
    api_key_env="GOOGLE_API_KEY",
)

CHAIN = (NEMOTRON_3_ULTRA, GEMINI_3_6_FLASH, GEMINI_3_5_FLASH)
