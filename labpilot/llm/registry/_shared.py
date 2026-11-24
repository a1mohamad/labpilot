"""What several gateways share."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider

OPENROUTER_REASONING: dict[str, object] = {"reasoning": {"effort": "high"}}


OPENAI_REASONING: dict[str, object] = {"reasoning_effort": "high"}


# LITEROUTER and ORCAROUTER - two more free gateways, measured 2026-09-23 and
# re-measured LIVE 2026-09-28 before any line here was written: all seven
# routes below answered, 21 of 21 calls, under three reasoning settings each.
#
# Only models ALREADY RANKED in CHAIN are routed here. Both gateways list more
# free models than this, and an unranked model cannot be placed - the same
# rule that kept dots-3-note and nex-n2.5 out on 2026-09-19.
#
# Their value is a SECOND and THIRD route to models whose first route is thin
# or dead: GLM-5.3 Flash (tier 1) is otherwise only on Cline, whose quota is
# invisible; DeepSeek V4 Flash died on OpenRouter AND Kilo; Mistral Medium's
# own account is paused until its monthly usage resets.
#
# LiteRouter sends no rate-limit headers, and it allows ONE concurrent request
# per account, measured as a 403 "Too many concurrent requests". Its DASHBOARD
# does publish a daily limit, per model - see _literouter below, which is why
# this note used to say "publishes no quota" and no longer does. A real report
# prompt fits: 48,011 tokens to DeepSeek and 27,010 to GLM-5.3 Flash, both 200.
#
# OrcaRouter publishes 10 requests a minute and 50 a day on its own
# /api/free-package/public, and took a 15,691-token report prompt.
#
# ONE pool per gateway for OrcaRouter, Kilo and Requesty: none of their limits
# is per model. LiteRouter is the exception, and test_registry pins it.
def _gateway(
    *,
    name: str,
    url: str,
    key: str,
    model: str,
    context_window: int,
    max_output_tokens: int,
    quota_pool: str | None = None,
    seconds_between_calls: float = 0.0,
    seconds_after_call: float = 0.0,
    max_concurrent: int | None = None,
    requests_per_minute: int | None = None,
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=url,
        model=model,
        api_key_env=key,
        quota_pool=quota_pool or key,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        seconds_between_calls=seconds_between_calls,
        seconds_after_call=seconds_after_call,
        max_concurrent=max_concurrent,
        requests_per_minute=requests_per_minute,
        # glm-5.3-flash returns EMPTY content without an explicit effort on
        # Cline and on OrcaRouter - a property of the model, not the host.
        extra_body=OPENROUTER_REASONING,
    )
