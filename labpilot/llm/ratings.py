"""One row per live tier: what the routes need to know about it (section 33).

WRITTEN BY A SCRIPT (scripts/routing/write_ratings.py) from the registry and
the speed logs; to add a tier, add its family there. `family` is the name
the bench measures it under.
strength 1-5: Artificial Analysis v5.0.1, older scores moved to that scale
(31.19). seconds: the median of the valid calls of the 5-call test; big_seconds:
the 4,000 and 20,000-token calls. per_day: calls a day of its quota pool,
shared by the tiers on that pool. penalty 0..1: failed calls in the test,
one call at a time, a low rate a minute, a pool shared with other users.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rating:
    family: str
    provider: str
    strength: int
    confidence: str
    seconds: float
    big_seconds: float
    valid: float
    per_day: int
    scarce: bool
    penalty: float


RATINGS: dict[str, Rating] = {
    "GLM-5.3 Flash (LiteRouter)": Rating(
        "GLM-5.3 Flash", "literouter", 4, "high", 4.0, 3.4, 1.0, 100, False, 0.1
    ),
    "GLM-5.3 Flash cheap (LiteRouter)": Rating(
        "GLM-5.3 Flash", "literouter", 4, "high", 3.0, 4.1, 1.0, 100, False, 0.1
    ),
    "DeepSeek V4.1 Flash 1017 (LiteRouter)": Rating(
        "DeepSeek V4.1 Flash", "literouter", 5, "high", 3.0, 2.9, 1.0, 100, False, 0.1
    ),
    "Hy4 preview (OrcaRouter)": Rating(
        "Hy4", "orcarouter", 5, "high", 29.8, 35.4, 1.0, 50, False, 0.05
    ),
    "Gemini 4 Hydrogen": Rating(
        "Gemini 4 Hydrogen", "google", 5, "high", 60.0, 70.0, 0.6, 20, True, 0.4
    ),
    "Gemini 4 Hydrogen (key 2)": Rating(
        "Gemini 4 Hydrogen", "google", 5, "high", 60.0, 70.0, 0.6, 20, True, 0.4
    ),
    "Gemini 4 Hydrogen (key 3)": Rating(
        "Gemini 4 Hydrogen", "google", 5, "high", 60.0, 70.0, 0.6, 20, True, 0.4
    ),
    "Gemini 3.8 Flash": Rating(
        "Gemini 3.8 Flash", "google", 5, "high", 257.0, 367.0, 0.6, 20, True, 0.4
    ),
    "Gemini 3.8 Flash (key 2)": Rating(
        "Gemini 3.8 Flash", "google", 5, "high", 257.0, 367.0, 0.6, 20, True, 0.4
    ),
    "Gemini 3.8 Flash (key 3)": Rating(
        "Gemini 3.8 Flash", "google", 5, "high", 257.0, 367.0, 0.6, 20, True, 0.4
    ),
    "Ling 3.1 Flash (Requesty)": Rating(
        "Ling 3.1 Flash", "requesty", 5, "high", 5.0, 6.8, 1.0, 50, False, 0.1
    ),
    "MiniMax M3.1 Flash (LiteRouter)": Rating(
        "MiniMax M3.1 Flash", "literouter", 5, "high", 2.2, 2.5, 1.0, 100, False, 0.1
    ),
    "MiniMax M3.1 Flash (Routeway)": Rating(
        "MiniMax M3.1 Flash", "routeway", 5, "high", 9.7, 10.7, 1.0, 25, False, 0.2
    ),
    "DeepSeek V4.1 Flash (Token Harbor)": Rating(
        "DeepSeek V4.1 Flash", "token_harbor", 5, "high", 4.2, 4.1, 1.0, 32, False, 0.0
    ),
    "DeepSeek V4.1 Flash (LiteRouter)": Rating(
        "DeepSeek V4.1 Flash", "literouter", 5, "high", 2.9, 3.4, 1.0, 100, False, 0.1
    ),
    "DeepSeek V4.1 Flash cheap (LiteRouter)": Rating(
        "DeepSeek V4.1 Flash", "literouter", 5, "high", 4.7, 7.0, 1.0, 100, False, 0.1
    ),
    "DeepSeek V4 Pro cheap (LiteRouter)": Rating(
        "DeepSeek V4 Pro", "literouter", 4, "medium", 27.0, 38.9, 1.0, 100, False, 0.1
    ),
    "DeepSeek V4 Pro 0813 (LiteRouter)": Rating(
        "DeepSeek V4 Pro", "literouter", 4, "medium", 4.2, 5.2, 1.0, 100, False, 0.1
    ),
    "DeepSeek V4 Flash (Token Harbor)": Rating(
        "DeepSeek V4 Flash", "token_harbor", 4, "medium", 4.7, 6.1, 1.0, 32, False, 0.0
    ),
    "DeepSeek V4 Flash (LiteRouter)": Rating(
        "DeepSeek V4 Flash", "literouter", 4, "medium", 4.1, 4.0, 1.0, 100, False, 0.1
    ),
    "DeepSeek V4 Flash cheap (LiteRouter)": Rating(
        "DeepSeek V4 Flash", "literouter", 4, "medium", 3.9, 3.9, 1.0, 100, False, 0.1
    ),
    "MiMo V2.6 Flash (Token Harbor)": Rating(
        "MiMo V2.6 Flash", "token_harbor", 4, "high", 5.8, 5.8, 0.8, 32, False, 0.2
    ),
    "Qwen3.8 27B": Rating(
        "Qwen3.8 27B", "cloudflare", 4, "high", 6.8, 5.7, 1.0, 6, False, 0.15
    ),
    "Qwen3.8 27B (Groq)": Rating(
        "Qwen3.8 27B Groq", "groq", 4, "high", 2.0, 2.0, 1.0, 143, False, 0.0
    ),
    "Gemini 3.6 Flash": Rating(
        "Gemini 3.6 Flash", "google", 4, "medium", 4.0, 7.1, 1.0, 20, True, 0.0
    ),
    "Gemini 3.6 Flash (key 2)": Rating(
        "Gemini 3.6 Flash", "google", 4, "medium", 4.0, 7.1, 1.0, 20, True, 0.0
    ),
    "Gemini 3.6 Flash (key 3)": Rating(
        "Gemini 3.6 Flash", "google", 4, "medium", 4.0, 7.1, 1.0, 20, True, 0.0
    ),
    "Nemotron 3 Ultra (Kilo)": Rating(
        "Nemotron 3 Ultra", "kilo", 3, "high", 5.7, 4.9, 1.0, 333, False, 0.1
    ),
    "Nemotron 3 Ultra": Rating(
        "Nemotron 3 Ultra", "openrouter", 3, "high", 6.6, 6.9, 1.0, 7, False, 0.1
    ),
    "Nemotron 3 Ultra (Requesty)": Rating(
        "Nemotron 3 Ultra", "requesty", 3, "high", 8.2, 9.6, 0.8, 50, False, 0.3
    ),
    "Gemini 3.5 Flash-Lite": Rating(
        "Gemini 3.5 Flash-Lite", "google", 3, "high", 2.9, 3.2, 1.0, 500, False, 0.0
    ),
    "Gemini 3.5 Flash-Lite (key 2)": Rating(
        "Gemini 3.5 Flash-Lite", "google", 3, "high", 2.9, 3.2, 1.0, 500, False, 0.0
    ),
    "Gemini 3.5 Flash-Lite (key 3)": Rating(
        "Gemini 3.5 Flash-Lite", "google", 3, "high", 2.9, 3.2, 1.0, 500, False, 0.0
    ),
    "MiniMax M2.7 (LiteRouter)": Rating(
        "MiniMax M2.7", "literouter", 3, "low", 6.6, 12.5, 1.0, 100, False, 0.1
    ),
    "Hy3 (LiteRouter)": Rating(
        "Hy3", "literouter", 3, "low", 17.1, 17.1, 1.0, 100, False, 0.1
    ),
    "Gemma 4 26B A4B": Rating(
        "Gemma 4 26B", "google", 2, "medium", 2.5, 3.1, 0.9, 14400, False, 0.1
    ),
    "Gemma 4 26B A4B (key 2)": Rating(
        "Gemma 4 26B", "google", 2, "medium", 2.5, 3.1, 0.9, 14400, False, 0.1
    ),
    "Gemma 4 26B A4B (key 3)": Rating(
        "Gemma 4 26B", "google", 2, "medium", 2.5, 3.1, 0.9, 14400, False, 0.1
    ),
    "DeepSeek V3.2 (LiteRouter)": Rating(
        "DeepSeek V3.2", "literouter", 2, "low", 3.6, 5.2, 1.0, 100, False, 0.1
    ),
    "Nemotron 3.5 Lightning (Kilo)": Rating(
        "Nemotron 3.5 Lightning", "kilo", 2, "medium", 5.4, 5.5, 1.0, 333, False, 0.1
    ),
    "Nemotron 3.5 Lightning (Cline)": Rating(
        "Nemotron 3.5 Lightning", "cline", 2, "medium", 6.8, 12.9, 1.0, 100, False, 0.1
    ),
    "Gemma 4 31B (Requesty)": Rating(
        "Gemma 4 31B", "requesty", 1, "medium", 11.2, 11.9, 0.8, 50, False, 0.3
    ),
    "Qwen 3.7 Flash (Bazaarlink)": Rating(
        "Qwen 3.7 Flash", "bazaarlink", 3, "low", 3.5, 3.5, 1.0, 30, False, 0.1
    ),
    "DeepSeek V4 Flash 0731 (Bazaarlink)": Rating(
        "DeepSeek V4 Flash 0731", "bazaarlink", 4, "low", 5.6, 5.9, 1.0, 30, False, 0.1
    ),
    "Ministral 8B": Rating(
        "Ministral 8B", "mistral", 1, "low", 1.8, 2.0, 1.0, 500, False, 0.3
    ),
    "Mistral Nemo": Rating(
        "Ministral 8B", "mistral", 1, "low", 1.5, 23.6, 1.0, 500, False, 0.3
    ),
    "Ministral 14B": Rating(
        "Ministral 14B", "mistral", 1, "low", 2.2, 2.4, 1.0, 1000, False, 0.3
    ),
    "Codestral": Rating(
        "Codestral", "mistral", 1, "low", 1.8, 2.8, 1.0, 1000, False, 0.3
    ),
    "Qwen3 Coder Next (LiteRouter)": Rating(
        "Qwen3 Coder Next", "literouter", 1, "low", 2.6, 2.7, 1.0, 100, False, 0.1
    ),
    "Qwen3 Next 80B (LiteRouter)": Rating(
        "Qwen3 Next 80B", "literouter", 1, "low", 2.9, 3.2, 1.0, 100, False, 0.1
    ),
    "MiMo V2.5 (Token Harbor)": Rating(
        "MiMo V2.5", "token_harbor", 4, "low", 5.5, 5.5, 1.0, 32, False, 0.0
    ),
    "Gemma 4 26B A4B Darksoul (Routeway)": Rating(
        "Gemma 26B Darksoul", "routeway", 2, "low", 4.0, 5.7, 1.0, 25, False, 0.2
    ),
    "Gemma 4 26B A4B Moonlight (Routeway)": Rating(
        "Gemma 26B Moonlight", "routeway", 2, "low", 2.0, 2.7, 1.0, 25, False, 0.2
    ),
    "Gemma 4 26B A4B Musica (Routeway)": Rating(
        "Gemma 26B Musica", "routeway", 2, "low", 3.6, 26.6, 1.0, 25, False, 0.2
    ),
    "Gemma 4 26B A4B Luminous (Routeway)": Rating(
        "Gemma 26B Luminous", "routeway", 2, "low", 5.1, 4.8, 1.0, 25, False, 0.2
    ),
    "Gemma 4 26B A4B Chimerax (Routeway)": Rating(
        "Gemma 26B Chimerax", "routeway", 2, "low", 4.5, 4.6, 1.0, 25, False, 0.2
    ),
    "Gemma 4 26B A4B MeroMero (Routeway)": Rating(
        "Gemma 26B MeroMero", "routeway", 2, "low", 6.4, 8.0, 1.0, 25, False, 0.2
    ),
    "North Mini Code (Kilo)": Rating(
        "North Mini Code", "kilo", 1, "medium", 2.6, 9.2, 1.0, 333, False, 0.1
    ),
    "North Mini Code": Rating(
        "North Mini Code", "openrouter", 1, "medium", 2.2, 3.2, 1.0, 7, False, 0.1
    ),
    "GPT-OSS 120B": Rating(
        "GPT-OSS 120B", "cloudflare", 1, "high", 30.0, 30.0, 0.3, 6, False, 0.85
    ),
    "GPT-OSS 120B (LiteRouter)": Rating(
        "GPT-OSS 120B", "literouter", 1, "high", 5.6, 5.6, 1.0, 100, False, 0.1
    ),
    "GPT-OSS 120B (Groq)": Rating(
        "GPT-OSS 120B", "groq", 1, "high", 1.7, 26.7, 1.0, 143, False, 0.0
    ),
    "GPT-OSS 20B (Groq)": Rating(
        "GPT-OSS 20B", "groq", 1, "low", 1.9, 1.9, 1.0, 143, False, 0.0
    ),
    "Gemini 3.1 Flash-Lite": Rating(
        "Gemini 3.1 Flash-Lite", "google", 2, "medium", 5.4, 5.4, 1.0, 500, False, 0.0
    ),
    "Gemini 3.1 Flash-Lite (key 2)": Rating(
        "Gemini 3.1 Flash-Lite", "google", 2, "medium", 5.4, 5.4, 1.0, 500, False, 0.0
    ),
    "Gemini 3.1 Flash-Lite (key 3)": Rating(
        "Gemini 3.1 Flash-Lite", "google", 2, "medium", 5.4, 5.4, 1.0, 500, False, 0.0
    ),
    "Gemma 4 31B": Rating(
        "Gemma 4 31B", "google", 1, "medium", 43.8, 43.8, 0.5, 14400, False, 0.5
    ),
    "Gemma 4 31B (key 2)": Rating(
        "Gemma 4 31B", "google", 1, "medium", 43.8, 43.8, 0.5, 14400, False, 0.5
    ),
    "Gemma 4 31B (key 3)": Rating(
        "Gemma 4 31B", "google", 1, "medium", 43.8, 43.8, 0.5, 14400, False, 0.5
    ),
    "GLM-5.3 Flash (OrcaRouter)": Rating(
        "GLM-5.3 Flash", "orcarouter", 4, "high", 4.8, 5.2, 1.0, 10, False, 0.05
    ),
    "DeepSeek V4.1 Flash (OrcaRouter)": Rating(
        "DeepSeek V4.1 Flash", "orcarouter", 5, "high", 3.8, 4.4, 1.0, 10, False, 0.05
    ),
    "DeepSeek V4 Flash (OrcaRouter)": Rating(
        "DeepSeek V4 Flash", "orcarouter", 4, "medium", 4.8, 4.9, 1.0, 10, False, 0.05
    ),
    "Hy3 (OrcaRouter)": Rating(
        "Hy3", "orcarouter", 3, "low", 30.0, 30.0, 0.3, 10, False, 0.75
    ),
    "Muse Glimmer 30B (Requesty)": Rating(
        "Muse Glimmer 30B", "requesty", 2, "medium", 99.0, 138.2, 0.8, 50, False, 0.3
    ),
    "Muse Glimmer 30B (Routeway)": Rating(
        "Muse Glimmer 30B", "routeway", 2, "medium", 30.0, 30.0, 0.3, 25, False, 0.9
    ),
}
