"""The tiers of Literouter."""

from __future__ import annotations

from labpilot.llm.openai_compatible import OpenAICompatibleProvider
from labpilot.llm.registry._shared import _gateway

LITEROUTER_URL = "https://api.literouter.com/v1/chat/completions"


# LiteRouter, read from its own dashboard and measured 2026-10-11.
#
#   daily limit   shown PER MODEL on every card: "Free tier (100)" for some ids
#                 and "(∞)" for others, so each model is its own pool, the way
#                 Google's are. This replaces the note above that said
#                 LiteRouter publishes no quota.
#   cooldown      7 seconds between messages for the ACCOUNT, answered with
#                 HTTP 403 (not 429) on any model. Measured: four models called
#                 back to back, one 200 and three refused; the same three
#                 answered when spaced 8 seconds apart. 8 is the measured
#                 value that worked, 7 is the number the error states.
LITEROUTER_SECONDS_BETWEEN_CALLS = 8.0


# One request at a time for the whole account (403 "Too many concurrent requests",
# 2026-10-11 and again with the product's own parallel nodes, 2026-11-11). The gap
# above does not stop it, because a call can run for a minute.
LITEROUTER_MAX_CONCURRENT = 1


# A call that started 0 s after another one ENDED was refused 403 although its
# start was 9 s after the other's start (measured 2026-11-16, 12 of 13 LiteRouter
# refusals were this text). So the account is also closed for a moment after a call.
LITEROUTER_QUIET_AFTER_CALL = 1.0


def _literouter(*, model: str, **kwargs) -> OpenAICompatibleProvider:
    return _gateway(
        url=LITEROUTER_URL,
        key="LITEROUTER_API_KEY",
        model=model,
        quota_pool=f"LITEROUTER_API_KEY:{model}",
        seconds_between_calls=LITEROUTER_SECONDS_BETWEEN_CALLS,
        seconds_after_call=LITEROUTER_QUIET_AFTER_CALL,
        max_concurrent=LITEROUTER_MAX_CONCURRENT,
        **kwargs,
    )


LITEROUTER_GLM_5_3_FLASH = _literouter(
    name="GLM-5.3 Flash (LiteRouter)",
    model="glm-5.3-flash:free",
    context_window=1_310_720,
    max_output_tokens=131_072,
)


# The free id was "deepseek-v4-flash-0731:free" until it left the catalogue
# (403 "not available or misspelled", 2026-10-11). The same model is listed
# without the date, and answered a 41,628-token prompt and a 32,000-token ask.
LITEROUTER_DEEPSEEK_V4_FLASH = _literouter(
    name="DeepSeek V4 Flash (LiteRouter)",
    model="deepseek-v4-flash:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


# THE REST OF LITEROUTER'S FREE DEEPSEEK, added 2026-10-11. Nine ids are listed
# free; all nine answered a 15.8K-token prompt, a 41.6K-token prompt and a
# 32,000-token output ask, one call at a time. Placed on Artificial Analysis
# v4.3.2, read from each model's own page:
#
#     DeepSeek V4.1 Flash   39   214 tok/s    ABOVE the V4 Flash it follows
#     DeepSeek V4 Pro       36    85 tok/s    (the page may be a newer build
#                                              than the free id - not checked)
#     DeepSeek V4 Flash     34   216 tok/s
#     DeepSeek V3.2         16*  (an estimate, "independent evaluation
#                                 forthcoming")
#
# THE "-cheap" AND "-stable" IDS: LiteRouter does not say what they are, and
# neither do we. They answered like their base ids, so each is placed right
# after its base as a second route to the same family. Nothing here claims they
# are the same weights; if one turns out to be a lower-quality serving, this is
# the place to move it. The dashboard shows "(inf)" daily on the cheap ids that
# were visible and 100 on the base ids.
#
# V3.1 and V3.2 are OLDER models and they did worst: both named the wrong class
# on the 15.8K prompt ("QuoraPreproccesor" for SystemConfig), V3.1 on the 41K one
# too. They sit at the bottom, V3.2 by its score and V3.1 unscored, last.
LITEROUTER_DEEPSEEK_V4_1_FLASH = _literouter(
    name="DeepSeek V4.1 Flash (LiteRouter)",
    model="deepseek-v4.1-flash:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_1_FLASH_STABLE = _literouter(
    name="DeepSeek V4.1 Flash stable (LiteRouter)",
    model="deepseek-v4.1-flash-stable:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_1_FLASH_CHEAP = _literouter(
    name="DeepSeek V4.1 Flash cheap (LiteRouter)",
    model="deepseek-v4.1-flash-cheap:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_PRO = _literouter(
    name="DeepSeek V4 Pro (LiteRouter)",
    model="deepseek-v4-pro:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_PRO_CHEAP = _literouter(
    name="DeepSeek V4 Pro cheap (LiteRouter)",
    model="deepseek-v4-pro-cheap:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_FLASH_CHEAP = _literouter(
    name="DeepSeek V4 Flash cheap (LiteRouter)",
    model="deepseek-v4-flash-cheap:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


# The V3 pair holds 128k on Artificial Analysis. 32,768 of output is what a
# 32,000-token ask was accepted at, not a measured ceiling.
LITEROUTER_DEEPSEEK_V3_2 = _literouter(
    name="DeepSeek V3.2 (LiteRouter)",
    model="deepseek-v3.2:free",
    context_window=131_072,
    max_output_tokens=32_768,
)


LITEROUTER_DEEPSEEK_V3_1 = _literouter(
    name="DeepSeek V3.1 (LiteRouter)",
    model="deepseek-v3.1:free",
    context_window=131_072,
    max_output_tokens=32_768,
)


# REPLACES "qwen3.8-27b:free", which left the free list (403 "not available or
# misspelled", 2026-10-11). This is NOT the same model: the 27B is gone and the
# list now holds Qwen3.8 Flash. Artificial Analysis scores the open checkpoint
# Qwen3.8-Flash-Next at 40 on v4.3.2 (reasoning), against 34 for the 27B, but
# it has no page under this exact name, so the match is unproven and the tier
# sits where the 27B sat. Measured 2026-10-11: a 40,892-token prompt answered
# correctly, but it took 157s once, against 6-15s for every other id tested.
LITEROUTER_QWEN_3_8_FLASH = _literouter(
    name="Qwen3.8 Flash (LiteRouter)",
    model="qwen3.8-flash:free",
    context_window=262_144,
    max_output_tokens=65_536,
)


# The 32,768 window and 29,491 output here came from OpenRouter's free route
# and were never measured on LiteRouter. Measured 2026-10-11: a 37,458-token
# prompt answered correctly and a 32,000-token output ask was accepted, so the
# window is larger than that and a report fits. Nothing above 37K was tried,
# which is why this is 131,072 and not the 200,000 the family is rated for.
LITEROUTER_GLM_5_2 = _literouter(
    name="GLM-5.2 (LiteRouter)",
    model="glm-5.2:free",
    context_window=131_072,
    max_output_tokens=65_536,
)


# MORE OF LITEROUTER'S FREE LIST, added 2026-10-11. Every id below answered a
# tiny prompt both with and without the `reasoning` field the registry sends,
# a 15.8K-token prompt correctly, a ~38K-token prompt, and a 32,000-token output
# ask, with no empty answer and no "<think>" leaking into the text (MiniMax M2.7
# did leak it on Routeway, which is why it was left out there). Scores are
# Artificial Analysis v4.3.2, each read from the model's own page:
#
#     GLM-5.3 Flash cheap   42   (the tier-1 model; a second LiteRouter id)
#     GLM-5.2 cheap         34   (a second id for the GLM-5.2 route above)
#     MiniMax M3            29       and its "-cheap" id
#     GLM-5                 28*  an estimate, and the page says deprecated
#     Kimi K2.6             27   the free list has only the "-cheap" id
#     GLM-5.1               26
#     Kimi K2.7 Code        26   again only "-cheap"; the 42 a search snippet
#                                gave was the OLD index (v4.1) - the page says 26
#     MiniMax M2.7          23
#
# LEFT OUT, because there is no independent score to place them by: MiniMax
# M3.1 Flash and Tencent Hy4 / Hy3 (Hy4 spent 1,000-1,600 tokens answering "you
# are online"). No evidence, no promotion. Windows below are what each family is
# rated for; none was tried above ~38K tokens.
LITEROUTER_GLM_5_3_FLASH_CHEAP = _literouter(
    name="GLM-5.3 Flash cheap (LiteRouter)",
    model="glm-5.3-flash-cheap:free",
    context_window=1_310_720,
    max_output_tokens=131_072,
)


LITEROUTER_GLM_5_2_CHEAP = _literouter(
    name="GLM-5.2 cheap (LiteRouter)",
    model="glm-5.2-cheap:free",
    context_window=131_072,
    max_output_tokens=65_536,
)


LITEROUTER_MINIMAX_M3 = _literouter(
    name="MiniMax M3 (LiteRouter)",
    model="minimax-m3:free",
    context_window=1_000_000,
    max_output_tokens=65_536,
)


LITEROUTER_MINIMAX_M3_CHEAP = _literouter(
    name="MiniMax M3 cheap (LiteRouter)",
    model="minimax-m3-cheap:free",
    context_window=1_000_000,
    max_output_tokens=65_536,
)


LITEROUTER_GLM_5 = _literouter(
    name="GLM-5 (LiteRouter)",
    model="glm-5:free",
    context_window=200_000,
    max_output_tokens=65_536,
)


LITEROUTER_KIMI_K2_6 = _literouter(
    name="Kimi K2.6 cheap (LiteRouter)",
    model="kimi-k2.6-cheap:free",
    context_window=262_144,
    max_output_tokens=65_536,
)


LITEROUTER_GLM_5_1 = _literouter(
    name="GLM-5.1 (LiteRouter)",
    model="glm-5.1:free",
    context_window=200_000,
    max_output_tokens=65_536,
)


LITEROUTER_KIMI_K2_7_CODE = _literouter(
    name="Kimi K2.7 Code cheap (LiteRouter)",
    model="kimi-k2.7-code-cheap:free",
    context_window=262_144,
    max_output_tokens=65_536,
)


LITEROUTER_MINIMAX_M2_7 = _literouter(
    name="MiniMax M2.7 (LiteRouter)",
    model="minimax-m2.7:free",
    context_window=204_800,
    max_output_tokens=65_536,
)


# REPLACES "mistral-medium-2508:free", which left the free list (403, 2026-10-11).
# Mistral Large 3 is the only large Mistral on it, and it is WEAK: AA v4.3.2 = 9
# (the page calls it deprecated), and on 2026-10-11 it named the wrong class on
# a 41K prompt ("QuoraPreproccesor" for SystemConfig). It goes at the very end
# of the live tiers, where it is only ever reached when everything better has
# failed.
LITEROUTER_MISTRAL_LARGE_3 = _literouter(
    name="Mistral Large 3 (LiteRouter)",
    model="mistral-large-3:free",
    context_window=262_144,
    max_output_tokens=32_768,
)


# ADDED 2026-11-02 after the free lists of every gateway were re-read through
# their own APIs and every new id probed (one call, up to 2 retries). 12 of the
# ids above had LEFT the free list (403 "not available or misspelled") and moved
# to KNOWN_DEAD; these are the free ids that answered and are worth a slot.
#
#   GLM-5.1 cheap   AA v4.3.2 = 26 (the GLM-5.1 score; the "-cheap" serving is
#                   not proven identical, as for every "-cheap" id here). 3.9 s.
#   Hy3             AA v4.3.2 = 23 (Hy3-preview, reasoning), a tie with
#                   Flash-Lite. 7.7 s here, 3.5 s on OrcaRouter. The window is
#                   what the family is rated for, not measured on this gateway.
#   Qwen3.8 Flash stable   the "-stable" twin of the tier above it. 6.1 s.
#   Qwen3 Coder Next / Qwen3 Coder   UNSCORED. AA shows 21 for Coder Next on
#                   index v4.1.1 and 9 on an older page, and 12 to 18 for the
#                   480B Coder, none of them on v4.3.2, so they go with the
#                   unscored tiers. 8.7 s and 7.0 s. Qwen was asked for.
LITEROUTER_GLM_5_1_CHEAP = _literouter(
    name="GLM-5.1 cheap (LiteRouter)",
    model="glm-5.1-cheap:free",
    context_window=204_800,
    max_output_tokens=131_072,
)


LITEROUTER_HY3 = _literouter(
    name="Hy3 (LiteRouter)",
    model="hy3:free",
    context_window=262_144,
    max_output_tokens=65_536,
)


LITEROUTER_QWEN_3_8_FLASH_STABLE = _literouter(
    name="Qwen3.8 Flash stable (LiteRouter)",
    model="qwen3.8-flash-stable:free",
    context_window=1_000_000,
    max_output_tokens=131_072,
)


LITEROUTER_QWEN3_CODER_NEXT = _literouter(
    name="Qwen3 Coder Next (LiteRouter)",
    model="qwen3-coder-next:free",
    context_window=262_144,
    max_output_tokens=235_929,
)


# GPT-OSS 120B on LiteRouter (added 2026-11-02 at the user's request): the same
# model as the Cloudflare and Groq tiers, 9.9 s live. A DELIBERATE 16,384 output
# cap, because no long answer was tried on this route, so it serves small jobs
# until one is. It goes after Cloudflare's route and before Groq's.
LITEROUTER_GPT_OSS_120B = _literouter(
    name="GPT-OSS 120B (LiteRouter)",
    model="gpt-oss-120b:free",
    context_window=131_072,
    max_output_tokens=16_384,
)


LITEROUTER_QWEN3_CODER = _literouter(
    name="Qwen3 Coder (LiteRouter)",
    model="qwen3-coder:free",
    context_window=262_144,
    max_output_tokens=65_536,
)


# ADDED 2026-11-08, after LiteRouter's free list was re-read and every new id was
# probed (one tiny call, `reasoning: high`, 8 s apart, up to 3 tries): all four
# answered on the FIRST try with a whole answer.
#
#   GLM-5.3 cheap         8.6 s   AA v4.3.2 = 42 is the GLM-5.3 Flash score; the
#                                 id has no "flash" in it, so the match is not
#                                 proven, like every "-cheap" id here
#   DeepSeek V4.1 Flash 1017      4.6 s   a dated build of the 39 model, placed
#                                 after the other V4.1 ids
#   DeepSeek V4 Flash 0731 stable 7.8 s   a build of the 34 model, after V4 Flash
#   MiMo V2.6 Flash       1.6 s   the fastest of the set. Scored the same day from
#                                 the AA v5.0.1 chart: 27 (see its CHAIN slot)
#
# Windows come from the catalogue (1,048,576 and 1,050,000); no output cap is
# published for MiMo, so 32,768 is a conservative guess, not a measurement.
LITEROUTER_GLM_5_3_CHEAP = _literouter(
    name="GLM-5.3 cheap (LiteRouter)",
    model="glm-5.3-cheap:free",
    context_window=1_048_576,
    max_output_tokens=131_072,
)


LITEROUTER_DEEPSEEK_V4_1_FLASH_1017 = _literouter(
    name="DeepSeek V4.1 Flash 1017 (LiteRouter)",
    model="deepseek-v4.1-flash-1017:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_FLASH_0731_STABLE = _literouter(
    name="DeepSeek V4 Flash 0731 stable (LiteRouter)",
    model="deepseek-v4-flash-0731-stable:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


# ADDED 2026-11-15 from LiteRouter's free list (GET /v1/models, ids ending ":free").
# Builds of families already scored, so each sits next to its base. The windows
# are what the catalogue lists (1,048,576); the output cap is the family's, not
# measured on these ids. Probed before they were kept (see the commit notes).
LITEROUTER_DEEPSEEK_V4_FLASH_0731 = _literouter(
    name="DeepSeek V4 Flash 0731 (LiteRouter)",
    model="deepseek-v4-flash-0731:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_FLASH_0731_CHEAP = _literouter(
    name="DeepSeek V4 Flash 0731 cheap (LiteRouter)",
    model="deepseek-v4-flash-0731-cheap:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_PRO_0813 = _literouter(
    name="DeepSeek V4 Pro 0813 (LiteRouter)",
    model="deepseek-v4-pro-0813:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


LITEROUTER_DEEPSEEK_V4_PRO_STABLE = _literouter(
    name="DeepSeek V4 Pro stable (LiteRouter)",
    model="deepseek-v4-pro-stable:free",
    context_window=1_048_576,
    max_output_tokens=393_216,
)


# UNSCORED, so it goes with the other unscored Qwen3 tiers. 262,144 is the
# catalogue window; the 65,536 output cap is a guess, like the Kimi ones above.
LITEROUTER_QWEN3_NEXT_80B = _literouter(
    name="Qwen3 Next 80B (LiteRouter)",
    model="qwen3-next-80b-a3b-instruct:free",
    context_window=262_144,
    max_output_tokens=65_536,
)


# MiniMax M3.1 Flash on LiteRouter, added the same day at the user's request:
# 1.9 s, whole answer, first try. Routeway's route of this model has a 42,000
# window and can never hold a report; LiteRouter lists 1,048,576. The 65,536 output
# cap is the MiniMax M3 figure above, not a measurement of this id.
LITEROUTER_MINIMAX_M3_1_FLASH = _literouter(
    name="MiniMax M3.1 Flash (LiteRouter)",
    model="minimax-m3.1-flash:free",
    context_window=1_048_576,
    max_output_tokens=65_536,
)


LITEROUTER_MIMO_V2_6_FLASH = _literouter(
    name="MiMo V2.6 Flash (LiteRouter)",
    model="mimo-v2.6-flash:free",
    context_window=1_050_000,
    max_output_tokens=32_768,
)
