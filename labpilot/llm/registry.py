from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

NEMOTRON_3_ULTRA = OpenAICompatibleProvider(
    name="Nemotron 3 Ultra",
    tier=1,
    url=OPENROUTER_URL,
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key_env="OPENROUTER_API_KEY",
)

CHAIN = (NEMOTRON_3_ULTRA,)
