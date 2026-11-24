"""The order of every tier: CHAIN, and the two lists it keeps last."""

from __future__ import annotations

import dataclasses

from labpilot.llm.gemini import GeminiProvider
from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry.bazaarlink import (
    BAZAARLINK_DEEPSEEK_V4_FLASH_0731,
    BAZAARLINK_QWEN_3_7_FLASH,
)
from labpilot.llm.registry.cline import (
    CLINE_BEAM_1_0,
    CLINE_GLM_5_3_FLASH,
    CLINE_LAGUNA_S_2_1,
    CLINE_NEMOTRON_3_5_LIGHTNING,
)
from labpilot.llm.registry.cloudflare import GPT_OSS_120B, QWEN_3_8_27B
from labpilot.llm.registry.google import (
    GEMINI_3_1_FLASH_LITE,
    GEMINI_3_5_FLASH_LITE,
    GEMINI_3_6_FLASH,
    GEMINI_3_8_FLASH,
    GEMINI_4_HYDROGEN,
    GEMMA_4_26B,
    GEMMA_4_31B,
    _other_accounts,
)
from labpilot.llm.registry.groq import (
    GPT_OSS_20B_GROQ,
    GPT_OSS_120B_GROQ,
    QWEN_3_8_27B_GROQ,
)
from labpilot.llm.registry.kilo import (
    KILO_DEEPSEEK_V4_FLASH,
    KILO_GLM_5_2,
    KILO_INKLING_SMALL,
    KILO_LAGUNA_S_2_1,
    KILO_LING_3_1_FLASH,
    KILO_NEMOTRON_3_5_LIGHTNING,
    KILO_NEMOTRON_3_SUPER,
    KILO_NEMOTRON_3_ULTRA,
    KILO_NORTH_MINI_CODE,
    KILO_QWEN_3_8_27B,
    KILO_STEP_3_7_FLASH,
)
from labpilot.llm.registry.literouter import (
    LITEROUTER_DEEPSEEK_V3_1,
    LITEROUTER_DEEPSEEK_V3_2,
    LITEROUTER_DEEPSEEK_V4_1_FLASH,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_1017,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_CHEAP,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_STABLE,
    LITEROUTER_DEEPSEEK_V4_FLASH,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_CHEAP,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_STABLE,
    LITEROUTER_DEEPSEEK_V4_FLASH_CHEAP,
    LITEROUTER_DEEPSEEK_V4_PRO,
    LITEROUTER_DEEPSEEK_V4_PRO_0813,
    LITEROUTER_DEEPSEEK_V4_PRO_CHEAP,
    LITEROUTER_DEEPSEEK_V4_PRO_STABLE,
    LITEROUTER_GLM_5,
    LITEROUTER_GLM_5_1,
    LITEROUTER_GLM_5_1_CHEAP,
    LITEROUTER_GLM_5_2,
    LITEROUTER_GLM_5_2_CHEAP,
    LITEROUTER_GLM_5_3_CHEAP,
    LITEROUTER_GLM_5_3_FLASH,
    LITEROUTER_GLM_5_3_FLASH_CHEAP,
    LITEROUTER_GPT_OSS_120B,
    LITEROUTER_HY3,
    LITEROUTER_KIMI_K2_6,
    LITEROUTER_KIMI_K2_7_CODE,
    LITEROUTER_MIMO_V2_6_FLASH,
    LITEROUTER_MINIMAX_M2_7,
    LITEROUTER_MINIMAX_M3,
    LITEROUTER_MINIMAX_M3_1_FLASH,
    LITEROUTER_MINIMAX_M3_CHEAP,
    LITEROUTER_MISTRAL_LARGE_3,
    LITEROUTER_QWEN3_CODER,
    LITEROUTER_QWEN3_CODER_NEXT,
    LITEROUTER_QWEN3_NEXT_80B,
    LITEROUTER_QWEN_3_8_FLASH,
    LITEROUTER_QWEN_3_8_FLASH_STABLE,
)
from labpilot.llm.registry.mistral import (
    CODESTRAL,
    DEVSTRAL_2,
    MAGISTRAL_SMALL,
    MINISTRAL_8B,
    MINISTRAL_14B,
    MISTRAL_MEDIUM,
    MISTRAL_NEMO,
)
from labpilot.llm.registry.openrouter import (
    DEEPSEEK_V4_FLASH,
    GLM_5_2,
    NEMOTRON_3_SUPER,
    NEMOTRON_3_ULTRA,
    NORTH_MINI_CODE,
)
from labpilot.llm.registry.orcarouter import (
    ORCAROUTER_DEEPSEEK_V4_1_FLASH,
    ORCAROUTER_DEEPSEEK_V4_FLASH,
    ORCAROUTER_GLM_5_3_FLASH,
    ORCAROUTER_HY3,
    ORCAROUTER_HY4_PREVIEW,
)
from labpilot.llm.registry.requesty import (
    REQUESTY_GEMMA_4_31B,
    REQUESTY_LING_3_1_FLASH,
    REQUESTY_MUSE_GLIMMER,
    REQUESTY_NEMOTRON_3_ULTRA,
)
from labpilot.llm.registry.routeway import (
    ROUTEWAY_DEEPSEEK_V4_FLASH,
    ROUTEWAY_GEMMA_VARIANTS,
    ROUTEWAY_MINIMAX_M3_1_FLASH,
    ROUTEWAY_MUSE_GLIMMER,
)
from labpilot.llm.registry.token_harbor import (
    TOKEN_HARBOR_DEEPSEEK_V4_1_FLASH,
    TOKEN_HARBOR_DEEPSEEK_V4_FLASH,
    TOKEN_HARBOR_MIMO_V2_5,
    TOKEN_HARBOR_MIMO_V2_6_FLASH,
)


def _ordered(*providers: GeminiProvider | OpenAICompatibleProvider):
    """Tier is the POSITION, never a number somebody typed.

    Reordering CHAIN without renumbering `tier=` was a real bug on 2026-08-11:
    the tuple was put in the right order while the fields kept their old
    values, so the chain read 2, 2, 3, 1, 4, 6 and only an invariant test
    noticed. Deriving it here makes that class of bug impossible rather than
    merely tested for.
    """
    return tuple(
        dataclasses.replace(provider, tier=position)
        for position, provider in enumerate(providers, 1)
    )


# Each Google model appears THREE times, on three accounts, adjacent. Adjacency
# is right here for the same reason the 2026-08-16 rewrite made it harmless: a
# spent pool is skipped for free, so a twin costs nothing when the first key
# still works and is the strongest available model when it does not. Ordering
# by capability then means "the same model on another account" beats
# "a weaker model on this one".
CHAIN = _ordered(
    # GLM-5.3 Flash on two gateways (its Cline route is KNOWN_DEAD since
    # 2026-11-03). OrcaRouter's route of it is in NOT_TRUSTED, at the tail.
    LITEROUTER_GLM_5_3_FLASH,
    LITEROUTER_GLM_5_3_FLASH_CHEAP,
    # MOVED UP 2026-11-08 on AA v5.0.1 (one page, one index, read from a
    # screenshot of the live chart): DeepSeek V4.1 Flash 1017 = 33, ahead of
    # Gemini 3.8 Flash (31) by two points, so a real gap and not a tie.
    LITEROUTER_DEEPSEEK_V4_1_FLASH_1017,
    # ADDED 2026-11-16: Hy4 preview on OrcaRouter answered 5 of 5 probes in 5.8 to
    # 7.0 s, and it has its OWN OrcaRouter allowance (50 a minute, 250 a day).
    # Its score is NOT settled: the v5.0.1 chart read on 2026-11-08 showed a "Hy4"
    # at 35, but whether that is this preview build is not proven, and 30.3 found
    # no score for the preview. So it goes just under the two models that are
    # scored on that page above it, and it is in no score table. Move it by the
    # live AA page.
    ORCAROUTER_HY4_PREVIEW,
    GEMINI_4_HYDROGEN,
    *_other_accounts(GEMINI_4_HYDROGEN),
    GEMINI_3_8_FLASH,
    *_other_accounts(GEMINI_3_8_FLASH),
    # ADDED 2026-11-02: Ling 3.1 Flash, AA v4.3.2 = 41 (a tie with Gemini 3.8
    # Flash), 2 s on both routes. On v5.0.1 it is 30 against Gemini 3.8's 31, still
    # a tie. (Kilo's route answers 404 since 2026-11-15 and waits in KNOWN_DEAD.)
    REQUESTY_LING_3_1_FLASH,
    # Gemini 3.7 Flash is NOT in the chain: Google redirects it to 3.8 (the reply's
    # modelVersion says "gemini-3.8-flash", checked 2026-11-16), so it was the
    # same model a second time under a different quota name.
    # MiniMax M3.1 Flash: AA v4.3.2 = 43 (a tie with Ling 41) but v5.0.1 = 29
    # (index v5 dropped GDPval), two points under Gemini 3.8 (31). It was first
    # at position 4 on the v4.3.2 number; both indexes agree it belongs after the
    # Gemini 3.8 and Ling tiers and before DeepSeek V4.1 Flash. LiteRouter's route
    # first: its 1M window can hold a report, Routeway's 42,000 never can and it
    # answers in about 30 s.
    LITEROUTER_MINIMAX_M3_1_FLASH,
    ROUTEWAY_MINIMAX_M3_1_FLASH,
    # --- ADDED 2026-10-11: DeepSeek on LiteRouter, by AA v4.3.2 -------------
    # V4.1 Flash (39) ties Gemini 3.7 Flash, and 3.7 is now served by 3.8 (41),
    # so it goes after the pair. Each "-stable" and "-cheap" id follows its base.
    # (The stable id, V4 Pro and the plain V4 Flash left the free list on
    # 2026-11-02 and wait in KNOWN_DEAD.) OrcaRouter's V4.1 Flash is in
    # NOT_TRUSTED.
    # ADDED 2026-11-16: Token Harbor's route first. The same model (AA 39), 2.8 to
    # 3.8 s on 5 of 5, 60 requests a minute and no concurrency limit, where
    # LiteRouter takes one request at a time and waits 8 s between calls.
    TOKEN_HARBOR_DEEPSEEK_V4_1_FLASH,
    LITEROUTER_DEEPSEEK_V4_1_FLASH,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_CHEAP,
    # REVIVED 2026-11-08: V4 Pro cheap answers again (V4 Pro is 36, between the
    # V4.1 Flash ids above and the V4 Flash ids below). Only the cheap id is on
    # the free list; the plain V4 Pro and the V4.1 Flash stable id stay dead.
    LITEROUTER_DEEPSEEK_V4_PRO_CHEAP,
    # ADDED 2026-11-15: two more builds of V4 Pro, after its cheap id.
    LITEROUTER_DEEPSEEK_V4_PRO_0813,
    # --- ADDED 2026-09-19, placed on TWO independent sources ---------------
    # DeepSeek first of the three: it and Qwen TIE on AA (35 vs 34, inside
    # the +-1 interval), Qwen wins Code Arena by 13 Elo, and DeepSeek is
    # FIVE TIMES faster (211.9 tok/s against 43.1) with a 1.05M context and
    # no per-day neuron budget. A 13-Elo coding edge does not buy a 5x
    # slowdown when generation is already 98.2% of an answer.
    #
    # Its two ORIGINAL routes died on 2026-09-23 and wait at the END of the
    # chain; the LiteRouter and Routeway ones followed on 2026-11-02.
    # REVIVED 2026-11-08: the plain V4 Flash id is free again; each "-cheap" and
    # "-stable" id follows its base.
    # ADDED 2026-11-16: Token Harbor's route of the same model first (5 of 5).
    TOKEN_HARBOR_DEEPSEEK_V4_FLASH,
    LITEROUTER_DEEPSEEK_V4_FLASH,
    LITEROUTER_DEEPSEEK_V4_FLASH_CHEAP,
    # ADDED 2026-11-16: MiMo V2.6 Flash = 27 on the AA v5.0.1 chart, two points
    # under MiniMax M3.1 Flash (29) and seven over Qwen3.8 27B (20). Its LiteRouter
    # route left the free list on 2026-11-15, so this is its only route.
    TOKEN_HARBOR_MIMO_V2_6_FLASH,
    # Then the coding specialist. It ties Gemini 3.6 Flash on general
    # intelligence and beats it by 56 Elo on code, which is the task this
    # project actually does - so it goes above it.
    # (Qwen3.8 Flash and MiMo V2.6 Flash left LiteRouter's free list on
    # 2026-11-15 and wait in KNOWN_DEAD.)
    QWEN_3_8_27B,
    # ADJACENT, for the same reason the Google twins are: once Cloudflare's
    # neurons are gone the strongest thing still available is the same model
    # on Groq, not a weaker one. It can never serve a report (8,000 tokens a
    # MINUTE), and _check_fits refuses it locally for free.
    QWEN_3_8_27B_GROQ,
    # (GLM-5.2 cheap, revived 2026-11-08, left the free list again 2026-11-15.)
    GEMINI_3_6_FLASH,
    *_other_accounts(GEMINI_3_6_FLASH),
    # Gemini 3.5 Flash is NOT in the chain either: Google redirects it to 3.6
    # (modelVersion "gemini-3.6-flash", checked 2026-11-16).
    # (Beam 1.0 on Cline answers 402 since 2026-11-15 and waits in KNOWN_DEAD.)
    KILO_NEMOTRON_3_ULTRA,
    NEMOTRON_3_ULTRA,
    REQUESTY_NEMOTRON_3_ULTRA,
    GEMINI_3_5_FLASH_LITE,
    *_other_accounts(GEMINI_3_5_FLASH_LITE),
    # AA 23, a tie with Flash-Lite, which has a measured allowance. (Hy3 has no
    # trusted route: LiteRouter's is dead and OrcaRouter's is in NOT_TRUSTED.)
    LITEROUTER_MINIMAX_M2_7,
    LITEROUTER_HY3,
    # (Muse Glimmer has no trusted route: both Requesty's and Routeway's are in
    # NOT_TRUSTED, 2026-11-16.)
    # Gemma 4 26B A4B, AA 17. Moved to NOT_TRUSTED on 2026-11-17 and BACK to
    # trusted the same day (the user's rule: trusted in 2 of 3 sittings; it
    # failed 0 of 2, then passed 5 of 5, then passed 4 of 5).
    GEMMA_4_26B,
    *_other_accounts(GEMMA_4_26B),
    # AA 16 (an estimate) sits between the Gemma 26B (17) and the 31B (15).
    LITEROUTER_DEEPSEEK_V3_2,
    # MOVED UP 2026-11-15 from the unscored tiers. Both routes answered the smoke
    # test (Kilo 6.4 s, Cline 3.6 s) and Cline's is its ONLY usable free model
    # now. Its score is NOT settled: Artificial Analysis's launch article says 24,
    # comparison pages say 13 and 16, and the model page says 6. 16 (the middle
    # reading that is not the outlier) puts it level with DeepSeek V3.2 and just
    # above the Gemma 4 31B (15). Kilo first (200 an hour), Cline second (no
    # published quota). Move it by the live AA page, not by this guess.
    KILO_NEMOTRON_3_5_LIGHTNING,
    CLINE_NEMOTRON_3_5_LIGHTNING,
    # (Gemma 4 31B on Google moved to NOT_TRUSTED on 2026-11-17. Requesty's route
    # of it answered 5 of 5 in 8 to 11 s, so it stays trusted.)
    REQUESTY_GEMMA_4_31B,
    # ADDED 2026-10-18, UNSCORED, so below the measured Gemma 4 31B. Qwen first:
    # it is the fast one (3s against 6-12s) and its tools, JSON and big prompts
    # are all tested. Both serve small jobs only - see BAZAARLINK above.
    BAZAARLINK_QWEN_3_7_FLASH,
    BAZAARLINK_DEEPSEEK_V4_FLASH_0731,
    # ADDED 2026-10-23, UNSCORED: see MINISTRAL_8B. Best recall first. Codestral
    # joined them 2026-11-02.
    MINISTRAL_8B,
    MISTRAL_NEMO,
    MINISTRAL_14B,
    CODESTRAL,
    # ADDED 2026-11-02, UNSCORED: AA shows 6 to 24 for Nemotron 3.5 Lightning
    # depending on the page, and none of the Qwen3 Coder pages is on v4.3.2.
    LITEROUTER_QWEN3_CODER_NEXT,
    LITEROUTER_QWEN3_NEXT_80B,
    # ADDED 2026-11-16, UNSCORED (no AA page was found for MiMo V2.5).
    TOKEN_HARBOR_MIMO_V2_5,
    # UNSCORED community finetunes, below the measured Gemma 4 31B on purpose.
    *ROUTEWAY_GEMMA_VARIANTS,
    KILO_NORTH_MINI_CODE,
    NORTH_MINI_CODE,
    GPT_OSS_120B,
    LITEROUTER_GPT_OSS_120B,
    GPT_OSS_120B_GROQ,
    GPT_OSS_20B_GROQ,
    GEMINI_3_1_FLASH_LITE,
    *_other_accounts(GEMINI_3_1_FLASH_LITE),
    # Unscored and the worst on the one question asked of it, so it goes
    # last of the unscored. Then the weakest scored tier we have (AA 9).
    # (Mistral Large 3 left LiteRouter's free list on 2026-11-15.)
    # NOT TRUSTED - see NOT_TRUSTED below. They answer, but not every time: after
    # every trusted tier and before every dead one.
    # Gemma 4 31B on Google, all three keys, moved here 2026-11-17 (three
    # sittings: it passed 2 of 4, then 1 of 3, then 5 of 5, but each call took 36
    # to 66 s, with 500 and 503 "high demand" in the first two sittings). It is
    # trusted in 1 of 3 sittings only. The 26B was trusted again in 2 of 3.
    GEMMA_4_31B,
    *_other_accounts(GEMMA_4_31B),
    ORCAROUTER_GLM_5_3_FLASH,
    ORCAROUTER_DEEPSEEK_V4_1_FLASH,
    ORCAROUTER_DEEPSEEK_V4_FLASH,
    ORCAROUTER_HY3,
    REQUESTY_MUSE_GLIMMER,
    ROUTEWAY_MUSE_GLIMMER,
    # KNOWN DEAD, KEPT ON PURPOSE - see KNOWN_DEAD below. Kilo before its
    # OpenRouter twin even here, so the day one revives the order is right.
    CLINE_GLM_5_3_FLASH,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_STABLE,
    LITEROUTER_DEEPSEEK_V4_PRO,
    ROUTEWAY_DEEPSEEK_V4_FLASH,
    LITEROUTER_GLM_5_2,
    LITEROUTER_MINIMAX_M3,
    LITEROUTER_MINIMAX_M3_CHEAP,
    LITEROUTER_GLM_5,
    LITEROUTER_KIMI_K2_6,
    LITEROUTER_GLM_5_1,
    LITEROUTER_KIMI_K2_7_CODE,
    CLINE_LAGUNA_S_2_1,
    KILO_LAGUNA_S_2_1,
    KILO_QWEN_3_8_27B,
    KILO_INKLING_SMALL,
    KILO_STEP_3_7_FLASH,
    KILO_NEMOTRON_3_SUPER,
    NEMOTRON_3_SUPER,
    KILO_GLM_5_2,
    GLM_5_2,
    KILO_DEEPSEEK_V4_FLASH,
    DEEPSEEK_V4_FLASH,
    MISTRAL_MEDIUM,
    MAGISTRAL_SMALL,
    DEVSTRAL_2,
    # 2026-11-15: nine LiteRouter ids that left its free list.
    LITEROUTER_GLM_5_3_CHEAP,
    LITEROUTER_QWEN_3_8_FLASH,
    LITEROUTER_QWEN_3_8_FLASH_STABLE,
    LITEROUTER_MIMO_V2_6_FLASH,
    LITEROUTER_GLM_5_2_CHEAP,
    LITEROUTER_GLM_5_1_CHEAP,
    LITEROUTER_QWEN3_CODER,
    LITEROUTER_MISTRAL_LARGE_3,
    CLINE_BEAM_1_0,
    KILO_LING_3_1_FLASH,
    LITEROUTER_DEEPSEEK_V4_PRO_STABLE,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_STABLE,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_CHEAP,
    LITEROUTER_DEEPSEEK_V3_1,
)


# NOT TRUSTED (defined by the user, 2026-11-16). A tier that is not dead, because
# it DOES answer sometimes, but whose answers FLUCTUATE: it answers once and
# refuses five times, so no route can count on it. Examples: Routeway's Muse
# Glimmer (71 s once, a closed connection the next time) and OrcaRouter's four
# capacity-limited models (429 "free model capacity is limited", Retry-After
# about 3 hours, while the same key got a 200 from Hy4 in the same minute).
#
# The rule is about RELIABILITY, not about the size of the quota: a provider with
# a small but steady allowance is trusted, and a big allowance that is often shut
# is not. Trusted examples: Gemini Flash-Lite, LiteRouter's models, the Mistral
# models, Groq, Cloudflare. A tier enters this list when it answered in some
# calls and failed in others on the smoke test; it leaves after it answers
# reliably on two different days (5 of 5, the way Hy4 did before it was added).
#
# A route uses these tiers LAST: after every trusted tier and before KNOWN_DEAD.
# Never first. As of 2026-11-16, from one smoke test and some direct calls.
NOT_TRUSTED = (
    *(p.name for p in (GEMMA_4_31B, *_other_accounts(GEMMA_4_31B))),
    ORCAROUTER_GLM_5_3_FLASH.name,
    ORCAROUTER_DEEPSEEK_V4_1_FLASH.name,
    ORCAROUTER_DEEPSEEK_V4_FLASH.name,
    ORCAROUTER_HY3.name,
    # Requesty's route answered 4 of 5 on 2026-11-16 but in 170, 101, 36 and 24 s,
    # plus a 504 after 303 s (2.3 s on 2026-11-02): too uneven for any route.
    REQUESTY_MUSE_GLIMMER.name,
    ROUTEWAY_MUSE_GLIMMER.name,
)


# Tiers that answer 404 on every call, KEPT so they can come back. Both free
# routes to each model died the same way, and the error says why:
#
#   DeepSeek V4 Flash   2026-09-23   OpenRouter "unavailable for free. The paid
#                                    version is available now"; Kilo "the
#                                    requested model does not exist"
#   GLM-5.2             2026-09-28   the same two answers, word for word
#
# A free model that disappears sometimes returns. A dead tier at the END costs
# one fast 404, and only once every live tier above it has failed; near the TOP
# it cost a request on EVERY report. Take a name out of this list only after
# that tier answers again - that is a claim, and a test holds you to it.
#
# THE THREE MISTRAL CHAT TIERS WERE ADDED 2026-10-05, and they are not dead
# the way the two above are. Mistral's own catalogue (GET /v1/models) says two
# of them are the SAME MODEL, which is why the calls were fine and the names
# were the problem:
#
#   mistral-medium-latest = Mistral Medium 3.5. Its aliases are mistral-medium,
#       -3, -3-5, -2604, magistral-medium-latest and the two vibe-cli ids.
#   mistral-small-latest  = Mistral Small 4 (mistral-small-2603). Its aliases
#       include magistral-small-latest.
#
# The old pinned ids are gone: every dated magistral-* and devstral-* id except
# devstral-2512 answers 400 "invalid model", and mistral-medium-2508 and
# mistral-small-2506 answer the same limit-0 429 as the new names. Mistral's
# changelog says it plainly:
# Medium 3.5 came out 2026-04-28 and Small 4 on 2026-03-16, Magistral and
# Devstral are listed as deprecated in favour of them, and "Devstral 2.0 moves
# to paid API access" (2026-01-27).
#
# On this account both models answer 429 with x-ratelimit-limit-req-minute: 0,
# on every one of the 40-odd calls made on 2026-10-05, while 11 other models
# answered 200 through the same key, the same network and the same request.
# reasoning_effort "none" does not change it, and the monthly allowance IS back
# ($0 of $10 used) - so this is not a spent quota. The admin Limits page even
# lists medium and small at 1 RPS; the API header is the truth, and the two
# disagree (request id 01a10b8a-8a6c-7754-b703-02ae7ed7b7ba is one for Mistral
# support).
#
# Moved to the END rather than deleted, like the two above, because Mistral may
# change what the free plan includes. Devstral 2 and Magistral Small have NO live
# route elsewhere, which test_registry names as an exception on purpose.
# 2026-11-02: TWENTY MORE, found by probing every tier (one call, up to 2
# retries) and re-reading each gateway's own free list. None of these ids is on
# its gateway's free list any more, and each answered an error on every call:
#
#   LiteRouter  403 "model is not available or misspelled" for DeepSeek V4.1
#               Flash stable, V4 Pro (+cheap), V4 Flash, GLM-5.2 (+cheap),
#               MiniMax M3 (+cheap), GLM-5, GLM-5.1, Kimi K2.6 cheap and Kimi
#               K2.7 Code cheap
#   Routeway    400 "No model found: deepseek-v4-flash:free"
#   Cline       Laguna S 2.1 answers HTTP 500 and is no longer on the free list
#   Kilo        404 for Laguna S 2.1, Qwen3.8 27B, Inkling Small, Step 3.7
#               Flash and Nemotron 3 Super
#   OpenRouter  404 "unavailable for free" for Nemotron 3 Super
#
# Gemini 3.8, 3.7 and Gemma 31B were 503 or timeouts the same day; that is
# Google's capacity, so they are NOT listed here.
# 2026-11-03: GLM-5.3 Flash on Cline answers HTTP 402 "insufficient_credits"
# (balance $0.01, total_spent 0). Cline moved it off its free list to Cline
# Pass (cline-pass/glm-5.3-flash), so it now costs credits. The LiteRouter and
# OrcaRouter routes above stay live.
#
# 2026-11-08: THREE REVIVED. LiteRouter's free list was re-read and DeepSeek V4
# Pro cheap, DeepSeek V4 Flash and GLM-5.2 cheap answered a live call again
# (6.4 s, 8.3 s, 6.1 s, first try), so they left this list and moved up the chain.
KNOWN_DEAD = (
    CLINE_GLM_5_3_FLASH.name,
    LITEROUTER_DEEPSEEK_V4_1_FLASH_STABLE.name,
    LITEROUTER_DEEPSEEK_V4_PRO.name,
    ROUTEWAY_DEEPSEEK_V4_FLASH.name,
    LITEROUTER_GLM_5_2.name,
    LITEROUTER_MINIMAX_M3.name,
    LITEROUTER_MINIMAX_M3_CHEAP.name,
    LITEROUTER_GLM_5.name,
    LITEROUTER_KIMI_K2_6.name,
    LITEROUTER_GLM_5_1.name,
    LITEROUTER_KIMI_K2_7_CODE.name,
    CLINE_LAGUNA_S_2_1.name,
    KILO_LAGUNA_S_2_1.name,
    KILO_QWEN_3_8_27B.name,
    KILO_INKLING_SMALL.name,
    KILO_STEP_3_7_FLASH.name,
    KILO_NEMOTRON_3_SUPER.name,
    NEMOTRON_3_SUPER.name,
    KILO_GLM_5_2.name,
    GLM_5_2.name,
    KILO_DEEPSEEK_V4_FLASH.name,
    DEEPSEEK_V4_FLASH.name,
    MISTRAL_MEDIUM.name,
    MAGISTRAL_SMALL.name,
    DEVSTRAL_2.name,
    # 2026-11-15: LiteRouter's GET /v1/models lists 37 ":free" ids and none of
    # these nine is among them (the dashboard agrees). Most were revived on
    # 2026-11-02 or 2026-11-08 and have left again. Qwen3.8 Flash may have been
    # renamed to "qwen-3.8-27b:free"; that id is not probed or added yet.
    LITEROUTER_GLM_5_3_CHEAP.name,
    LITEROUTER_QWEN_3_8_FLASH.name,
    LITEROUTER_QWEN_3_8_FLASH_STABLE.name,
    LITEROUTER_MIMO_V2_6_FLASH.name,
    LITEROUTER_GLM_5_2_CHEAP.name,
    LITEROUTER_GLM_5_1_CHEAP.name,
    LITEROUTER_QWEN3_CODER.name,
    LITEROUTER_MISTRAL_LARGE_3.name,
    # 2026-11-15 (smoke test of every tier): Cline moved Beam 1.0 off its free
    # list (402 insufficient_credits) and Kilo answers 404 for Ling 3.1 Flash.
    # Ling still has a live route on Requesty; Beam has none we use (Kilo lists
    # reflection/beam-free, which is NOT probed or added).
    CLINE_BEAM_1_0.name,
    KILO_LING_3_1_FLASH.name,
    # 2026-11-20: LiteRouter's free list (33 ids) no longer lists these five,
    # and each answered 403 "not available or misspelled". Hy3 is back on the
    # list and answered, so it left this list the same day.
    LITEROUTER_DEEPSEEK_V4_PRO_STABLE.name,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_STABLE.name,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731.name,
    LITEROUTER_DEEPSEEK_V4_FLASH_0731_CHEAP.name,
    LITEROUTER_DEEPSEEK_V3_1.name,
)
