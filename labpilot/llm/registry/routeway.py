"""The tiers of Routeway."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider

ROUTEWAY_URL = "https://api.routeway.ai/v1/chat/completions"


# ROUTEWAY — a fourth free gateway, probed LIVE 2026-09-29 with
# scripts/models/probe_routeway.py before any line here was written.
#
# THE LIMITS ARE THE DECISION. Every number is from the API, not a docs page:
#
#     5 requests a MINUTE and 200 a DAY, read from the response headers, and the
#     day counter fell across DIFFERENT models - one budget, so one pool.
#
#     a hard context cap per free route, enforced on prompt PLUS requested
#     output and named in the 400:
#         deepseek-v4-flash:free   42,000   (the model itself holds 1,000,000)
#         the Gemma variants       62,000
#     A 41,901-token prompt passed and a 45,954-token one was refused. So the
#     window is both the context AND the output ceiling, and `max_tokens:
#     131072` on a ten-token prompt is a 400.
#
# WHAT WAS ADDED, and what was measured against it:
#   * DeepSeek V4 Flash - 3 of 3 whole answers to a real question, 2-11s, a
#     correct diagnosis of the planted bug, and a tool call in 2.4s. It cannot
#     serve a report (42,000 against the 58,000 one needs), which
#     CONTEXT_TOO_SMALL in the tests names. A third live route to a model whose
#     two original ones died.
#   * Six Gemma 4 26B A4B variants - 18 of 18 pings and 5 of 6 real answers (the
#     sixth was a proxy timeout at 10.2s, not the model). Routeway's own
#     description calls them COMMUNITY CREATIVE FINETUNES, so they are NOT the
#     stock model AA scores at 17, and none has a score of its own. They sit
#     below the measured Gemma 4 31B (15) on purpose: no evidence, no promotion.
#     The order among them rests on ONE sample each and means nothing.
#
# WHAT WAS LEFT OUT, and why:
#   * MiniMax M2.7 - AA 23, but 0 of 3 whole answers. Its reasoning arrives as
#     `<think>...` INSIDE the reply text, it spends 550-1,024 tokens on one
#     sentence, and one call took 58s. `_visible_text` would return the thinking
#     as the answer.
#   * Muse Glimmer 30B - 0 of 3 whole (one cut at 1,024 tokens after 57s, two
#     60s read timeouts, and an earlier 502). Requesty's route answered in 2.3s.
#
# THE TIMEOUT IS SET PER TIER, which is what the field exists for. Routeway
# HANGS instead of refusing (three DeepSeek calls ran past 60s, one Gemma
# prompt of 59K did too), and the default 600s read timeout would let one hang
# spend two thirds of the 900s chain budget. Real answers were 1-26s.
#
# A `cache-status: MISS/HIT` header shows Routeway caches identical requests.
# temperature is 0 here, so a repeated prompt can be served without a model.
ROUTEWAY_DEEPSEEK_TIMEOUT = (10.0, 120.0)


ROUTEWAY_GEMMA_TIMEOUT = (10.0, 180.0)


# Its response headers: x-ratelimit-limit-minute 5 and limit-day 200 for the account
# (read 2026-09-29 and again 2026-11-16).
ROUTEWAY_REQUESTS_PER_MINUTE = 5


def _routeway(
    *,
    name: str,
    model: str,
    context_window: int,
    timeout: tuple[float, float],
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=ROUTEWAY_URL,
        model=model,
        api_key_env="ROUTEWAY_API_KEY",
        # ONE pool: 5 a minute and 200 a day are account-wide across models.
        quota_pool="ROUTEWAY_API_KEY",
        requests_per_minute=ROUTEWAY_REQUESTS_PER_MINUTE,
        context_window=context_window,
        # No separate output cap exists. The server checks prompt PLUS output
        # against one window, and that window is what _check_fits enforces.
        max_output_tokens=context_window,
        timeout=timeout,
        # No `extra_body`: `reasoning_effort` is NOT in these models'
        # supported_parameters (only Muse Glimmer lists it), and an unlisted
        # field is a guess.
    )


ROUTEWAY_DEEPSEEK_V4_FLASH = _routeway(
    name="DeepSeek V4 Flash (Routeway)",
    model="deepseek-v4-flash:free",
    context_window=42_000,
    timeout=ROUTEWAY_DEEPSEEK_TIMEOUT,
)


# ADDED 2026-11-02 (the DeepSeek id above is GONE: 400 "No model found"; the
# replacement id deepseek-v4.1-flash:free is listed free but timed out on 5 of 5
# tries at 120 s, so it is NOT added - retest later with a short timeout).
#
#   MiniMax M3.1 Flash  AA v4.3.2 = 43 (the comparison pages on that index; the
#       current v5.0 page says 29). Probed 29.5 s for a one-line answer, so it
#       is slow for small jobs, and the catalogue window is 42,000, so it can
#       NEVER serve a report (CONTEXT_TOO_SMALL names it). It sits in the 42-41
#       group, a tie by this project's rule, and not first, because a 30-second
#       tier at position 1 would slow every small call that it answers.
#   Muse Glimmer 30B   AA v4.3 = 18, the model Requesty serves. 13.0 s here,
#       131,072 window. An earlier probe (2026-09-29) lost 3 of 3 answers to
#       timeouts, so it is the SECOND route, after Requesty's.
ROUTEWAY_MINIMAX_M3_1_FLASH = _routeway(
    name="MiniMax M3.1 Flash (Routeway)",
    model="minimax-m3.1-flash:free",
    context_window=42_000,
    timeout=ROUTEWAY_DEEPSEEK_TIMEOUT,
)


ROUTEWAY_MUSE_GLIMMER = _routeway(
    name="Muse Glimmer 30B (Routeway)",
    model="muse-glimmer-30b:free",
    context_window=131_072,
    timeout=ROUTEWAY_DEEPSEEK_TIMEOUT,
)


def _routeway_gemma(variant: str) -> OpenAICompatibleProvider:
    return _routeway(
        name=f"Gemma 4 26B A4B {variant} (Routeway)",
        model=f"gemma-4-26b-a4b-it-{variant.lower()}:free",
        context_window=62_000,
        timeout=ROUTEWAY_GEMMA_TIMEOUT,
    )


# Named first-sample-correct first (they read `xs[i-k:i+1]` as k+1 elements,
# the planted bug). ONE call each, so treat the order as a coin flip.
ROUTEWAY_GEMMA_VARIANTS = tuple(
    _routeway_gemma(variant)
    for variant in (
        "Darksoul",
        "Moonlight",
        "Musica",
        "Luminous",
        "Chimerax",
        "MeroMero",
    )
)
