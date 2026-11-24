# Section 30: chain update and provider limits

[Docs home](../README.md)

### 30. THE CHAIN UPDATE OF 2026-11-02 — dead tiers moved, new models added

*Done at the user's request, in this order: probe every tier, read every gateway's own free list, probe every new free id, rank the new models, then edit the chain, the tests and the docs. Exit AS58212 dataforest, Google 200 (probed first). `labpilot/llm/registry.py` and `tests/unit/llm/test_registry.py` changed; Claude typed them at the user's explicit request (an exception to "the user types the product code"). Nothing is committed.*

#### 30.1 What was measured

- **The first pass (86 tiers, 1 call each, 60 s read timeout, 2 retries for a temporary fault, no retry for 400/403/404 or a 429 with limit 0): 50 alive, 36 not.** The Google tiers that failed (Gemini 3.8 and 3.7 on all three keys, Gemma 31B on all three) were 503, a 500 or a read timeout, which is Google's capacity, so they were NOT moved.
- **The free lists** were read from each gateway's own API (Kilo, Requesty, LiteRouter, OrcaRouter, Routeway, Bazaarlink, OpenRouter, Cline's public list, and the Groq and Mistral model lists). Then every free chat id that was not in `CHAIN` was probed once (45 ids; Bazaarlink and OpenRouter extras were NOT probed, their daily quotas are tiny).
- **Routeway's `deepseek-v4.1-flash:free` is listed free and does not answer:** 5 of 5 tries timed out at 120 s with no HTTP status. It was NOT added; retest it later with a short timeout. LiteRouter's dashboard (a screenshot of its free list) agrees with its API.
- **Cline's free list is 4 ids now**, and `reflection/beam-free` (1.4 s) and `nvidia/nemotron-3.5-lightning-free` (3.3 s) answer; `cline-free/nemotron-3.5-super-vl`, `solar-mini4`, `solar-pro4` and `deepseek-v4.1-flash` are 403.

#### 30.2 Dead tiers: 20 moved to `KNOWN_DEAD` (it has 27 names now)

`KNOWN_DEAD` stays at the TAIL of `CHAIN` in chain order, and each family without another live route is named in `NO_LIVE_ROUTE` in the registry tests.

| gateway | tiers moved | what the provider answered |
|---|---|---|
| LiteRouter (12) | DeepSeek V4.1 Flash stable, V4 Pro and V4 Pro cheap, V4 Flash, GLM-5.2 and cheap, MiniMax M3 and cheap, GLM-5, GLM-5.1, Kimi K2.6 cheap, Kimi K2.7 Code cheap | 403 "not available or misspelled": left the free list |
| Routeway (1) | DeepSeek V4 Flash | 400 "No model found" |
| Cline (1) | Laguna S 2.1 | HTTP 500, off the free list |
| Kilo (5) | Laguna S 2.1, Qwen3.8 27B, Inkling Small, Step 3.7 Flash, Nemotron 3 Super | 404 |
| OpenRouter (1) | Nemotron 3 Super | 404 "unavailable for free" |

The seven names that were already there (GLM-5.2 and DeepSeek V4 Flash on Kilo and OpenRouter, Mistral Medium, Magistral Small, Devstral 2) stay.

#### 30.3 Ranking the new models (Artificial Analysis, read through search results 2026-11-02)

**The index moved: AA is on v5.0 now, and v4.3.2 numbers, which this file's whole table uses, only survive on older model pages and on comparison pages.** v5.0 dropped GDPval-AA, so the same model shows a different number (MiniMax-M3.1-Flash 43 on v4.3.2 and 29 on v5.0; Beam 30 and 18; Ling 3.1 Flash 41 and 29). Only v4.3.2 numbers are placed beside the old ones.

| model | v4.3.2 | placed | note |
|---|---|---|---|
| MiniMax-M3.1-Flash | 43 | tier 5 (Routeway) | tie with GLM-5.3 (42) by the one-point rule; not first because it answers in about 30 s and its free window is 42,000 so it can never write a report |
| Ling 3.1 Flash | 41 | after Gemini 3.8 (Kilo, then Requesty) | 2.0 s and 2.3 s; the 41 is on comparison pages for "Ling 3.1 Flash", the catalogue id is the 1019 build whose own page says 29 on v5.0, so the match of the two names is not proven |
| DeepSeek V4.1 Flash on OrcaRouter | 39 | after the LiteRouter V4.1 ids | 2.3 s, 50 a day |
| Beam 1.0 (Cline) | 30 | after Gemini 3.5 Flash | small jobs only (16,384 output cap, window not measured on Cline) |
| GLM-5.1 cheap (LiteRouter) | 26 (GLM-5.1's score) | before Flash-Lite | the "-cheap" serving is not proven identical |
| Hy3 (LiteRouter, OrcaRouter) | 23 (Hy3-preview) | with MiniMax M2.7 | 7.7 s and 3.5 s |
| Muse Glimmer 30B (Routeway) | 18 | after the Requesty route | 13 s; Routeway lost 3 of 3 answers to timeouts on 2026-09-29, so it is the second route |
| Qwen3.8 Flash stable (LiteRouter) | - | after Qwen3.8 Flash | 6.1 s, twin of the tier above |
| Nemotron 3.5 Lightning (Cline, Kilo) | 6, 13, 16, 24 on different pages | unscored | no number trusted |
| Qwen3 Coder Next, Qwen3 Coder (LiteRouter) | 21 on v4.1.1, 9 and 12-18 on older pages | unscored | none on v4.3.2 |
| Codestral (Mistral), GPT-OSS 20B (Groq) | not found | unscored, small jobs | Codestral recall .79 in the 2026-10-22 size test |
| GPT-OSS 120B (LiteRouter) | not found | unscored, small jobs | 9.9 s; the same model as the Cloudflare and Groq tiers; added at the user's request with a 16,384 output cap (no long answer tried) |

Not added, on purpose: Hy4-preview (no score, 53 s), MiniMax M2/M2.1/M2.5 (older than the M2.7 already there), the LiteRouter Qwen3 30B/32B/Next 80B (about 10 to 12 on old pages), Llama 3.3 70B and the small Ministrals, Kilo's Nemotron 3 Nano Omni (about 10), and Routeway's `deepseek-v4.1-flash:free` (does not answer).

#### 30.4 Code and tests

- `registry.py`: 17 new tier definitions (`CLINE_BEAM_1_0`, `CLINE_NEMOTRON_3_5_LIGHTNING`, `KILO_LING_3_1_FLASH`, `KILO_NEMOTRON_3_5_LIGHTNING`, `REQUESTY_LING_3_1_FLASH`, `LITEROUTER_GLM_5_1_CHEAP`, `LITEROUTER_HY3`, `LITEROUTER_QWEN_3_8_FLASH_STABLE`, `LITEROUTER_QWEN3_CODER_NEXT`, `LITEROUTER_QWEN3_CODER`, `ORCAROUTER_DEEPSEEK_V4_1_FLASH`, `ORCAROUTER_HY3`, `ROUTEWAY_MINIMAX_M3_1_FLASH`, `ROUTEWAY_MUSE_GLIMMER`, `GPT_OSS_20B_GROQ`, `CODESTRAL`, `LITEROUTER_GPT_OSS_120B`), `CHAIN` rebuilt, **`CHAIN` is 103 tiers (was 86)**. No old constant was removed, so scripts that import them still work.
- `tests/unit/llm/test_registry.py`: `AA_SCORES` (the dead families out, six new in), `NO_LIVE_ROUTE` (17 names with reasons), `OUTPUT_TOO_SMALL` (Beam, Codestral, GPT-OSS 20B), `CONTEXT_TOO_SMALL` (MiniMax M3.1 Flash), the reasoning excuse lists (Routeway x2, Codestral) and the Cline served list.
- **Run: 401 tests passed** (`tests/unit/llm`, `test_smoke_live`, `test_measure_latency`, `test_public_api`, `test_architecture`, `test_packaging`, and the API tests that read the chain), `ruff check` and `ruff format --check` clean on the two changed areas. No smoke test, and the full suite was not run (the user asked for the changed tests only). **No deliberate break (mutation test) was run on the edited lists.**
- No new environment variable, so `.env.example` and `smoke.yaml` did not change.

#### 30.5 Open

- The three Google families that failed (Gemini 3.8, 3.7, Gemma 31B) need a retest on another day.
- Probes skipped on purpose: OpenRouter's `gemma-4-26b/31b-it:free`, `inkling:free`, `nemotron-3.5-lightning:free` (50 a day) and Bazaarlink's `ling-3.1-flash-1019` and `nemotron-3.5-lightning-free`.
- The AA numbers come from search results, not from reading each page; the Ling, Beam and MiniMax M3.1 Flash placements are the three that rest on v4.3.2 comparison pages and should be read on the model pages before anyone leans on them.
- The weekly smoke run has not run these new tiers; `test_gateway_tiers_are_free.py` (live) will check that the new gateway ids are still free.
- Speed is unmeasured at report length for every new tier.

#### 30.6 LiteRouter re-read, four tiers added and three revived — 2026-11-08

*Free lists of Kilo, LiteRouter, Routeway and Cline were re-read through their own APIs; Routeway and Token Harbor DeepSeek and the new LiteRouter ids were probed (one short call, up to 3 to 5 tries). Only LiteRouter was changed in code, at the user's request. Claude typed the registry and test edits (an exception to "the user types the product code"). No test was run, by the user's order. Nothing is committed.*

**Probe results (single short calls, not quality):**

| gateway | model | result |
|---|---|---|
| Routeway | `muse-glimmer-30b:free`, `minimax-m3.1-flash:free` | answered on try 3 (24 s, 22 s); the first two tries were 10 s tunnel timeouts |
| Routeway | `deepseek-v4.1-flash:free` | FAILED 5 of 5 twice (90 s hangs and one 502): listed free, does not answer, NOT added |
| Token Harbor | `deepseek-v4-flash:free`, `deepseek-v4.1-flash:free` | both OK first try (7.9 s, 5.2 s). **NOT added: it has no provider wiring.** The code reads `TOKEN_HARBOR_API`, which was a revoked key (401); `TOKEN_HARBOR_API_KEY` worked. The user removed the wrong key. Base URL is in `.env.example`: `https://tokenharbor.ai/v1` |
| LiteRouter | `glm-5.3-cheap`, `glm-5.2-cheap`, `deepseek-v4.1-flash-1017`, `deepseek-v4-flash-0731-stable`, `deepseek-v4-flash`, `deepseek-v4-pro-cheap`, `mimo-v2.6-flash` (all `:free`) | **7 of 7 answered on the first try**, 1.6 to 8.6 s |

**Changed in `labpilot/llm/registry.py`:**
- Four NEW tiers: `GLM-5.3 cheap` (after `GLM-5.3 Flash cheap`), `DeepSeek V4.1 Flash 1017` (after the V4.1 cheap id), `DeepSeek V4 Flash 0731 stable` (after V4 Flash cheap) and `MiMo V2.6 Flash` (unscored, with the unscored LiteRouter tiers, after Qwen3 Coder). MiMo's 32,768 output cap is a guess, not a measurement.
- Three REVIVED, out of `KNOWN_DEAD` and up the chain: `DeepSeek V4 Pro cheap` (AA 36, after the V4.1 ids), `DeepSeek V4 Flash` (AA 34, before its cheap id) and `GLM-5.2 cheap` (AA 34, before Gemini 3.6 Flash). The plain `V4 Pro`, `GLM-5.2` and the V4.1 stable id stay dead. `KNOWN_DEAD` has 25 names now, `CHAIN` 107 tiers.
- Not scored on AA: the "-cheap" and dated builds are placed by their base model's score, which is NOT proven identical.

**Changed in `tests/unit/llm/test_registry.py`:** `AA_SCORES` gained `DeepSeek V4 Pro cheap` (36) and `GLM-5.2 cheap` (34); `NO_LIVE_ROUTE` lost those two names (a name there must be in `KNOWN_DEAD`). The other registry tests read the chain, so they need no edit, but they were NOT run.

**Later the same day (the user's screenshot of the AA v5.0.1 chart, 29 models on ONE page):** `MiniMax M3.1 Flash (LiteRouter)` was probed (1.9 s, first try) and added; 65,536 output is the M3 figure, not measured. v5.0.1 scores read from the chart: DeepSeek V4.1 Flash 1017 = 33, GLM-5.3 (max) 32, Gemini 3.8 Flash 31, Ling 3.1 Flash 30, MiniMax-M3.1-Flash 29, MiMo-V2.6-Flash 27, Qwen3.8 27B 20, Beam 1.0 18 (also Hy4 35, Inkling 2 Small 31, Mistral Large 4 26, Nemotron 3.5 Super VL 14). v5 dropped GDPval, so these differ from the v4.3.2 numbers (MiniMax M3.1 Flash 43 then, 29 now): **the two indexes are kept in two tables and never mixed.** Order changes made from it, each a real gap of two or more points: `DeepSeek V4.1 Flash 1017` moved up to just after the GLM-5.3 tiers (above Gemini 3.8); both MiniMax M3.1 Flash routes moved from position 4 to after the Gemini 3.7 tiers (LiteRouter first, then Routeway); `MiMo V2.6 Flash` moved out of the unscored tiers to just before Qwen3.8 27B. `CHAIN` has 112 tiers (108 until Token Harbor joined, 2026-11-16). Tests: `test_registry.py` has a second table `AA_V5_SCORES` and a test that orders those seven families by it (the v4.3.2 test still holds). Not run.

**Left over from the same sweep (not done):** Kilo's new free ids (`nvidia/nemotron-3.5-super-vl:free`, `nvidia/nemotron-3-nano-omni...`, `dots-3-note-preview:free`, stealth models) were not probed. Three LIVE tiers are no longer on their gateway's free list and should be probed and moved to `KNOWN_DEAD`: `Ling 3.1 Flash (Kilo)`, `Qwen3.8 Flash stable (LiteRouter)` and `Hy3 (LiteRouter)`. Cline's new `cline-free/*` ids are the 403 client-gated namespace.

---

#### 30.7 Rate limits, waits and other limits of every provider — researched 2026-11-11, for slice 11

*Written at the user's request: slice 11 (routing) builds a spreader that sends each call to a tier with room, so it must know, for every provider, how many requests a minute it takes, how long to wait between requests, and every other limit. Sources are named for each row. "Search" means a web search on 2026-11-11 whose result pages were read through the search tool, not the provider's page opened by hand; "measured" means our own call or the provider's own header; "code" means the value already in `labpilot/llm/registry.py`. A row marked weak must be measured again before slice 11 relies on it.*

**The limits that exist, in the words of a spreader.** A provider can limit: (1) requests per minute; (2) requests per day (or hour, or month); (3) input or output tokens per minute; (4) a minimum wait between two requests; (5) how many requests may be open at the same time; (6) the context window of a free route; (7) a pool that is shared with other users (a 429 that is nobody's fault); (8) a hang instead of a refusal. One provider often has three or four of them at once.

| provider (gateway key) | requests per minute | per day / hour / month | tokens | wait or concurrency | pool shape | source and strength |
|---|---|---|---|---|---|---|
| **Google AI Studio** (`GOOGLE_API_KEY`, `_2`, `_3`) | Flash 5; Flash-Lite 15; Gemma 30; embedding 100 | Flash **20/day**; Flash-Lite 500; Gemma 14,400; embedding 1,000 (one TEXT counts as one request); the day resets at midnight Pacific | 250K input a minute for Flash and Flash-Lite; **16K input a minute for Gemma** (each (key, model) is a room); embedding 30K | none | per project **and per model**; our 3 keys are 3 projects; keys in one project share | measured on the AI Studio rate-limit page (2026-08-16, 2026-08-28) and by live 429s. A search on 2026-11-11 found that Google no longer publishes per-model numbers in the public docs; the AI Studio page and the Rate Limits API are the only source. Gemini 3.7 and 3.8 answer 503 often. The Gemma limit counts input only |
| **Groq** (`GROQ_API_KEY`) | 30 | 1,000/day for gpt-oss-120b and Qwen3.8 27B; 200K tokens/day | **8,000 tokens/min counting the prompt AND the reserved output**; Qwen3.8 27B also limited to **1,000 output tokens/min** (measured 2026-11-02) | none | per organisation | search (copies of Groq's limits page) agrees with our measured 1,000/day and 8,000/min. The 30 RPM is from search only (weak); the old 60 RPM figure is for qwen3-32b |
| **OpenRouter** (`OPENROUTER_API_KEY`) | **20** for `:free` | **50/day** under $10 of credits ever bought, 1,000/day after | none stated | none | **per account**; more keys or accounts add nothing; a negative balance gives 402 even on free models | provider docs through search, and our own account (`is_free_tier`, 2026-08-10). Free routes also share an upstream pool with all users: 429 `upstream_provider_shared_pool` (measured 2026-09-19) is congestion, not our quota |
| **Cloudflare Workers AI** (`CLOUDFLARE_API_KEY`) | 300 for text generation (one aggregator; **weak**) | **10,000 neurons/day**, resets 00:00 UTC; a hard stop above it | cost is in neurons: 909 for one report on GPT-OSS 120B (about 11 a day); 244 for a 4,860-token call on Qwen3.8 27B (about 41 a day) | none | per account | the 10,000 is Cloudflare's pricing page (search); the neuron costs are ours (measured) |
| **Mistral** (`MISTRAL_API_KEY`) | codestral 125; ministral-8b 188; Nemo 188; ministral-14b 30; ministral-3b 750 (header `x-ratelimit-limit-req-minute`) | monthly token cap exists, number unknown | codestral 625K, 8b 625K, 14b 937.5K, 3b 1.3M a minute | none | per model; Medium, Small, Magistral and Devstral answer 429 with **limit 0** (not entitled, will not reset) | measured 2026-10-22 and 2026-11-02. The help centre says "1 request per second, 500K tokens per minute, per organisation"; that disagrees with the headers and **the headers win** (the console page is not an entitlement, 16.4) |
| **Kilo gateway** (`KILO_API_KEY`) | none stated | **200 requests/hour per IP** for free models, anonymous or signed in | none | none | **per IP address**, and our exit IP is a shared VPN address, so other people spend it too. Underneath, each free model has a daily cap on OpenRouter's shared capacity (Inkling Small: 1,000 a day for the whole world) | Kilo's own docs through search (official), plus our 429 bodies |
| **LiteRouter** (`LITEROUTER_API_KEY`) | none stated | a daily number **for each model** on the dashboard ("Free tier (100)" or "(inf)"), 2026-10-11 | none | **one request at a time for the account (403 "Too many concurrent requests") and at least 7 s between messages for the whole account, on ANY model (403 "Rate limit exceeded for your tier (7 seconds between messages)")**. Code waits **8 s** (`LITEROUTER_SECONDS_BETWEEN_CALLS`) | per model for the day, per account for the gap | measured 2026-10-11 and read from the dashboard. The web search on 2026-11-11 found **nothing** about LiteRouter, so no outside source exists. Calls that time out on OUR side can still run on THEIR side and keep the slot (10.4) |
| **OrcaRouter** (`ORCAROUTER_API_KEY`) | **10** | **50/day** | none | none | one pool for the account (code: 1 pool) | its own `GET /api/free-package/public` (2026-09-23). Answers 429 `free_rate_limited` when the free capacity is full (seen 2026-10-24) |
| **Routeway** (`ROUTEWAY_API_KEY`) | **5** | **200/day** | none | none | **one budget for every model**; one 429 retires all its tiers (13.4) | confirmed by Routeway's own rate-limit page through search (2026-11-11) and by response headers (2026-09-29). Also: a hard context window for each free route (42,000 / 62,000 / 131,072 tokens counted over prompt plus output), identical requests are cached for 1 hour, and the gateway **drops a request at about 121 s** (a hang, not a refusal), so tiers carry a 120 or 180 s read timeout |
| **Requesty** (`REQUESTY_API_KEY`) | none stated | docs: **50/day** for a new organisation, 200 for a paying one, across all free models together; the marketing pages say 200 with no card | none | none | one pool | **the two official pages disagree** (search, 2026-11-11). Measured: nothing yet (we never spent the day). Plan with 50 until measured |
| **Bazaarlink** (`BAZAARLINK_API_KEY`) | 10 per free model, 20 for the account tier | **60 UNITS/day for the whole account**; a unit grows with the prompt (429 after 13 calls of about 70,000 tokens, 22.2) | counted in units | none | account-wide although the docs say per model | its docs page and our run (2026-10-18) |
| **Cline** (`CLINE_API_KEY`) | unknown | unknown | unknown | none | per tier in code | Cline publishes no number and sends **no rate-limit headers**. Search (2026-11-11): the docs say free models work only in the IDE extension and the CLI; our API calls to `reflection/beam-free` and `nvidia/nemotron-3.5-lightning-free` do answer. GLM-5.3 Flash moved to Cline Pass and answers 402 |
| **Cohere** (`COHERE_API_KEY`, rerank and embed) | **10 per minute** on a trial key (Cohere's "Going Live" page); other sites say 5 or 20 | **1,000 calls a MONTH** for the key, shared by chat, embed and rerank (search, third-party; weak) | embed about 100K tokens/min (measured in slice 8, 2026-09-16) | none | per key | the 10 per minute is official; the monthly number is from our own earlier reading of the dashboard headers (`x-endpoint-monthly-call-limit: 1000`, `x-trial-endpoint-call-limit: 10`) |
| **Voyage** (`VOYAGE_API_KEY`) | **3** without a payment method (2,000 or 6,000 after, docs disagree) | none | **10,000 tokens/min**, counted whole per call; the 200M free tokens cover series-3 models only | none | per key | MongoDB's Voyage docs through search (2026-11-11) agree with our dashboard reading (2026-09-11) |
| **Jev** (OpenRouter route, or the Netlify proxy) | not stated | OpenRouter: paid, $0.042 per million input tokens; Netlify: 300 credits a month, 15 credits per production deploy | none | none | the OpenRouter key | measured (12.7, 2026-09-29) |

**What slice 11's spreader has to be able to say, from this table.**
1. **A gap between two calls for a whole account** (LiteRouter 8 s). Already in code as `seconds_between_calls`.
2. **At most N requests open at once for an account** (LiteRouter: 1). **Not in code.** The graph sends 4 to 8 calls at the same time, so a parallel step on LiteRouter is refused today. The chain only retries a refused call; it never queues.
3. **Requests per minute** for an account or a (key, model): Routeway 5, Gemini Flash 5, OrcaRouter 10, Cohere 10, Gemini Flash-Lite 15, OpenRouter 20, Groq 30, Gemma 30, Voyage 3. Today the chain learns it from a 429 and waits.
4. **Tokens per minute for a room:** Gemma 16K input per (key, model); Groq 8K prompt-plus-output, and 1,000 output for Qwen3.8 27B; Voyage 10K per call. A call larger than the room can never pass, so this one also decides **which node can use which tier** (see 29.24, the pure cost of each node).
5. **A daily count** for a pool: Gemini Flash 20, Flash-Lite 500, Gemma 14,400, Groq 1,000, OpenRouter 50, Routeway 200, OrcaRouter 50, Requesty 50 or 200, Bazaarlink 60 units, Cloudflare 10,000 neurons. The chain already retires a pool for the rest of the request after a 429 that resets later than 60 s, but it forgets it on the next request.
6. **A count per hour for an IP** (Kilo 200). Shared with every other user of our VPN exit.
7. **A hang limit** for providers that hang and do not refuse (Routeway about 121 s): a short read timeout for each tier. Already in code for Routeway only.
8. **A shared upstream pool that says 429 for no reason of ours** (OpenRouter free, Kilo free): treat as "try the next route", never as "our day is spent".

**What is NOT known, so slice 11 must measure it:** Cline's real quota; Requesty's real daily number; LiteRouter's per-model daily numbers and whether its 7 s and "one at a time" rules still hold; Cloudflare's 300 per minute; Groq's 30 per minute; Cohere's monthly number on this key today. The cheapest way is to read the headers the provider sends (`x-ratelimit-*`) on one call, and to spend a day on purpose for the ones that publish nothing.
