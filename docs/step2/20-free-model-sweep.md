# Section 20: the free model list moves

[Docs home](../README.md)

### 20. THE FREE MODEL LIST MOVES — the sweep of 2026-10-11

*Exit `130.185.120.132` and later `185.204.171.216`, both **AS57568 ARVANCLOUD**, Frankfurt, Google 200. The
work was done on branch `feat/literouter-models` (7 commits). On 2026-10-11 the user re-committed it onto `main`
piece by piece: the docs first (`62c42fb`), then `8b956d6`, `e65ecc6`, `aca8a3d`, `b35de66` and
`852d761`. `main` and the branch hold identical code and tests (checked with git). The branch is kept.*

#### 20.1 The sweep, and what failed

One tiny prompt to every tier, up to 3 retries after 2s, 5s and 10s, only for a temporary fault (429, 500,
502, 503 or a network fault). **43 of 56 answered.** The 13 that did not: 7 already in `KNOWN_DEAD`, Inkling
Small (the shared world-wide daily cap, resets 00:00 UTC), and five that were NOT known dead: three LiteRouter
ids that left the free list (fixed in 20.4) and **two Kilo tiers, Qwen3.8 27B and Step 3.7 Flash, that Kilo no
longer lists as free.** The weekly check `test_gateway_tiers_are_free` fails for exactly those two and passes
for every other gateway. **THEY ARE STILL IN THE CHAIN, left on purpose** (not asked for); moving them to
`KNOWN_DEAD` needs Step 3.7 Flash in `NO_LIVE_ROUTE` too.

**"OK" meant only that some text came back.** Two OK tiers gave poor answers: DeepSeek V4 Flash on Routeway
repeated one sentence and took 162s, and Gemma 4 31B on both Google keys wrote its own reasoning into the
answer. A first run of the script said every key was unset: `load_dotenv()` searches from the SCRIPT's folder,
not the working directory (`find_dotenv(usecwd=True)` fixes it). It spent no quota.

#### 20.2 Gemini 3.5 Flash and 3.7 Flash are REDIRECTED — and our logs would not say so

Google emailed that `gemini-3.5-flash` and `gemini-3.7-flash` are deprecated and "auto-redirected" to 3.6 and
3.8. The calls still return 200, so the sweep reported both as fine. Google's own reply says what answered:

```
we ask for gemini-3.5-flash -> "modelVersion": "gemini-3.6-flash"
we ask for gemini-3.7-flash -> "modelVersion": "gemini-3.8-flash"
control: gemini-3.5-flash-lite and gemini-3.1-flash-lite answer with their own name
```

`LLMResult.model` shows the name we ASKED for, so a report served by 3.8 is labelled 3.7. **NOT DECIDED**
(the user: "never mind" to the usage-page test): read `modelVersion` into the result, and move the two old
names to the end beside the dead tiers, since they now duplicate 3.6 and 3.8.

**Whose daily allowance a redirected call spends is UNKNOWN.** The AI Studio Rate Limit page showed 3.6 = 2,
3.7 = 1, 3.8 = 1 and no 3.5 row. If both redirects were charged to the new model, 3.8 would read 2; no single
rule fits those numbers, and the page may simply be late. Do not state it either way.

#### 20.3 LiteRouter, read from its own dashboard

- **A 7-second cooldown between messages for the whole ACCOUNT**, answered with **HTTP 403, not 429**, on any
  model: four models called back to back gave one 200 and three refusals, and the same three answered 8s
  apart. The old "403 Too many concurrent requests" note was this, not concurrency.
- **A daily limit shown PER MODEL** ("Free tier (100)" or "(inf)") — the registry said "publishes NO quota".
  So LiteRouter tiers now own a pool each (`LITEROUTER_API_KEY:<model>`), the way Google's do.
- **The free catalogue is `GET /v1/models` filtered on `:free`: 56 ids** (the dashboard says 55). It lists
  more than DeepSeek: GLM, MiniMax, Kimi, Qwen, Hunyuan, Mistral, gpt-oss.

Code: `HTTPProvider.seconds_between_calls` (zero by default) and `llm/_pacing.py`. The turn is RESERVED under a
lock and the sleep happens outside it, so parallel nodes get different slots; it is taken after the fit check
and after the key check, so a refused call or a missing key spends no turn. 8 tests, 8 mutations.

#### 20.4 What was changed, and the evidence

| change | evidence |
|---|---|
| `deepseek-v4-flash-0731:free` -> `deepseek-v4-flash:free` | a rename; same model |
| `qwen3.8-27b:free` -> `qwen3.8-flash:free` | a DIFFERENT model (Flash-Next scores 40 on v4.3.2 against 34 for the 27B, but it has no page under this name); keeps the 27B's slot. One 41K call took 157s |
| `mistral-medium-2508:free` -> `mistral-large-3:free` | a different, weak model: AA 9, deprecated, named the wrong class on a 41K prompt. The last live tier |
| `glm-5.2:free` window 32,768 -> 131,072 | the 32K came from OpenRouter's route; LiteRouter's took a 37,458-token prompt. It can serve a report now |
| nine DeepSeek ids | V4.1 Flash 39, V4 Pro 36, V4 Flash 34, V3.2 16*; V3.1 unscored |
| GLM-5.3 Flash cheap, GLM-5.2 cheap, MiniMax M3 (+cheap), GLM-5 28*, Kimi K2.6 27, GLM-5.1 26, Kimi K2.7 Code 26, MiniMax M2.7 23 | all on AA **v4.3.2**, each read from the model's own page |

Every added id answered a tiny prompt with and without the `reasoning` field, a 15.8K prompt correctly, a
~38-41K prompt, and a 32,000-token output ask, with no empty answer and no `<think>` in the text. **A search
snippet said Kimi K2.7 Code scores 42; that was the old v4.1 index, and the model's own page says 26.** Always
read the score and its index version from the page. The `-cheap` and `-stable` ids: LiteRouter does not say
what they are and neither do we; each sits right after its base. **Left out for want of an independent
score: MiniMax M3.1 Flash and Tencent Hy4 / Hy3** (Hy4 spent 1,000-1,600 tokens answering "you are online").

`test_the_models_we_scored_are_ordered_by_their_artificial_analysis_score` pins the order, with the scores as
literals and a gap of one point treated as a tie. **CHAIN is 73 tiers, 22 on LiteRouter.** Offline: 1101
passed, 5 skipped. Live: all 22 LiteRouter tiers answered through the real provider code in 189s.

#### 20.5 Open

- The Gemini redirect (20.2) and the two dead Kilo tiers (20.1).
- **Seven LiteRouter tiers sit in a row** (DeepSeek, positions 9-15). If LiteRouter fails fast, the chain
  waits 8s before each of them. Bounded by the 900s budget, and each tier has its own pool.
- **Report-length speed of the new tiers is NOT measured**, and Qwen3.8 Flash's 157s is one sample.
- The `-cheap` / `-stable` meaning, and whether the daily limits on the dashboard are enforced per model.
- The Chain 1 table in this file is stale (it lists 40 tiers); read `CHAIN`.
