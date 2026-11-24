# Section 15: slice 1, every tier ranked by speed

[Docs home](../README.md)

### 15. SLICE 1 IS MEASURED — every tier ranked by speed, 2026-09-30

*Full write-up: `docs/step2/slice1/RESULTS.md`. Instrument:
`scripts/models/measure_latency.py` with `tests/unit/test_measure_latency.py`.
**COMMITTED on `main`** (script `b4fa84a`, its tests `2f0ce0b`, the results
`0cc24d8`; this line said "NOT COMMITTED" after they were). The raw data is
`artifacts/step2/latency/2026-09-29_18-29.jsonl` (git-ignored).*

**50 tiers, 300 requests, plus 41 re-measured.** Two fixed jobs (a ~30-token gate
verdict and a ~500-token explanation), three rounds, one request at a time, no
retries. Exit AS24940 Hetzner, Nuremberg; Google 200 on both keys first.

#### 15.1 WHAT IT FOUND

```
route beats model   GPT-OSS 120B    Groq 4.1s     vs Cloudflare 30.2s    (7x)
                    GLM-5.3 Flash   Cline 8.3s    vs OrcaRouter 66.2s    (8x)
                    Qwen3.8 27B     Groq 8.3s     vs Cloudflare 83.7s    (10x)
                    CHAIN orders the routes of ONE model by quota, never by speed
newest Gemini       3.7 Flash 0 of 12 answered, 3.8 Flash 3 of 12, 3.6 Flash 5 of 12
                    - positions 4-7 of CHAIN answered 3 of 24 calls. 3.5 Flash and
                    both Flash-Lites: 36 of 36
thinking = the      Gemini 3.5 Flash wrote 566 tokens for a 30-token verdict, 529 of
fixed cost          them reasoning. Speed matters less than how much a tier thinks
same tier varies    North Mini Code (Kilo): 18.6s, 9.8s, 4.3s for the same job.
                    Three samples give a median, not a promise
```

**TIER 1 IS NOT SLOW AT THIS SIZE, and at report length it is only partly
explained.** GLM-5.3 Flash (Cline) wrote ~500 tokens in 8.3s, about 59 tokens a
second. The report-length probe (15.5) gave **3,794 tokens in 120s AND in 24s** -
five times apart on the same job - so the 119-497s reports are NOT reproduced:
either they were 21,000-38,000 tokens long or the tier was in its slow mode. This
run cannot say which.

#### 15.2 THREE THINGS THAT WERE WRONG ON THE WAY, all mine

- **The network was read as the model.** Through the VPN a tunnel that does not
  open in 10s is reported as `Read timed out (read timeout=10.0)`. The first run
  counted 41 of 300 as slow or failed models; 20 were in the last 25 calls. They
  are now kind `network`, retried, and never counted. `--fill FILE` re-runs only
  what a saved run is missing. **The 41 were measured ~2 hours after the rest.**
- **A line through two points is only as good as their distance.** A thinking tier
  writes the same number of tokens for both probes, so the fitted slope said 86s
  per 1,000 tokens for an answer that took 10s. The fit is now drawn only when the
  probes differ by 200+ tokens, and the ranking is on MEASURED seconds.
- **My first draft of the write-up had several wrong numbers** (`24 of 24` for
  `36 of 36`, "five" for six tiers that never answered, a Mistral count, a
  DeepSeek time) until each claim was checked against the data. **Check a summary
  against the file it summarises.**

#### 15.3 TWO DEFECTS THE DATA POINTED AT - the first FIXED 2026-09-30

- **An error inside an HTTP 200 was misreported. FIXED** in
  `labpilot/llm/openai_compatible.py` (commits 9364cc5, c71b4e5, 577ea95).
  Nemotron 3 Ultra and Super on OpenRouter and Kilo answered 200 with
  `{"message": "Upstream error from Nvidia: Service temporarily overloaded",
  "code": 503, ...}` where `choices` should be. Our reader said "unexpected
  response shape" and cut the body, so the REASON was lost and the chain saw a
  failure with no status instead of a **503, which the six-way rule retries**.
  Now the provider's message and its numeric code as `status` survive, a hidden
  503 is retried on the same tier, the metadata rate-limit headers are read (a
  hidden daily 429 retires the pool), and a reply with real `choices` is NEVER
  thrown away. 18 tests, 11 deliberate breaks, all caught.
- **Step 3.7 Flash (Kilo) spends a 2,048-token budget thinking.** 3 of 4 raw
  replies were `finish_reason: length`, `content: ""`, 8,000-9,000 characters of
  reasoning, for a 30-token answer. It is a property of the tier at a small budget,
  not a flaky endpoint. Qwen on Cloudflare and Groq and Laguna on Kilo also
  returned empty answers; their raw replies were NOT captured.

#### 15.4 WHAT IT DOES NOT TELL YOU

A second time of day (failures cluster, so gaps under ~30% are noise); the
rerankers (deliberately NOT re-measured - the slice 6 numbers stand: Flash-Lite
~1.3s, Jev 1.2-1.6s, Gemma 26B ~19s, Gemma 31B ~23s); the four known-dead routes;
and Mistral's speed, since all three Mistral-hosted tiers answered 429 on every
call. **The original 300 samples carry no timestamp; every new one does.**

**35 mutations on the script's rules (13 network and fill, 6 fit guard and ranking,
8 report probe, 8 zero-token guard and token-cap flag), every one fired on the
test meant to catch it - three survived first (a report cap inside `measure`, a
report ranking that quietly used the long time, and the long-probe zero filter) and
each got its own test.** 96 unit tests for the script.

#### 15.5 REPORT LENGTH, measured 2026-09-30

`--probes report`: a ~2,000-word report, 420s read cap, 8,192 tokens of room. **26
tiers, 2 samples each, 52 requests**, 22:05-22:55 UTC, same ISP. Table and detail:
`docs/step2/slice1/RESULTS.md` section 6.

```
fast, ~15-20s      Gemini 3.5 Flash-Lite x2, 3.1 Flash-Lite x2  (~3,000-4,700 tokens)
                   Groq 9-10s - but it STOPPED AT 4,000 TOKENS (an 8,000-token window)
medium, ~35-55s    Nemotron 3 Super, North Mini Code, Mistral Medium (LiteRouter),
                   DeepSeek V4 Flash, Qwen3.8 27B (LiteRouter), Gemini 3.5 Flash
                   (cut at 8,188 tokens, mostly reasoning)
over 100s          GLM-5.3 Flash on LiteRouter and OrcaRouter, GPT-OSS on Cloudflare,
                   ALL THREE Gemma 4 31B routes (and 4 of 8 calls HTTP 500 on key 1)
speed HELD         23 of 25 tiers wrote at least as many tokens a second at report
                   length as at 500. A report's time ~ its tokens / the tier's speed
Routeway           its gateway DROPS a request at ~121s (502 twice at 121.4 and
                   121.6). At 22 tok/s its six Gemma finetunes cannot write a report
```

**Two flaws in my own first table, both fixed before it was written down.** Eight
results were CUT AT THE TOKEN CAP (their seconds are the time to the cap, not to a
finished report) and one LiteRouter sample reported `completion_tokens: 0` for an
11,159-character answer, which halved that tier's speed. Both are now handled
(`usage_tokens` treats a reported zero as missing; the table says "cut at the token
cap xN").

#### 15.6 GEMMA IS NOT A BUG OF OURS - and one of our notes was wrong

Asked 2026-09-30 whether the Gemma tiers hide a bug. Direct calls and streaming:

```
Gemma 4 31B on Google   first token at 38.5s, done at 45.0s - the wait is BEFORE it
                        writes anything (Flash-Lite: 1.7s). As shipped, 3 of 6 calls
                        answered HTTP 500. Hidden reasoning 166-207 tokens for a 38-token answer
Gemma 4 26B A4B        7.1-7.3s as shipped, first token at 2.0s, no error in 5 calls
thinkingLevel MINIMAL  ACCEPTED - the 26B took 2.3-2.6s (3 of 3), no hidden tokens
thinkingLevel HIGH     accepted
LOW, MEDIUM, budget 0  400 "not supported for this model"
```

Causes: the 31B is a DENSE 31-billion-parameter model behind a queue ("small" is the
wrong word - the 26B A4B is the small one and is ~4x faster on Google); Gemma
thinks by default; and Routeway's six finetunes are slow because of their host (22
tok/s). **The 2026-09-11 note said Gemma refuses every request carrying a thinking
field. False: it accepts MINIMAL and HIGH and refuses LOW and MEDIUM, and MEDIUM
was what every Gemini tier shipped with.** Corrected in `registry.py`.

**DONE 2026-09-30, on the user's decision: `GEMMA_4_26B` IS IN THE CHAIN with
`thinking="MINIMAL"`** - CHAIN is now **56 tiers**, and tiers 32 and 33 are the 26B
on the two Google keys, between Muse Glimmer (AA 18) and the 31B (AA 15), at its own
17 (commits d87b539, 29ddcc9). Called through our own provider code: **2.1-2.2s on
both keys**; a longer job through `LLMClient` finished in 9.4s. Its own 14,400
requests a day, against Flash-Lite's 500.

- The 31B stays `thinking=None`, below it. **The reranker is unchanged**: it builds
  its tier with `thinking=None` itself, and a test fails if the chain's level ever
  reaches it.
- **NOT tested for answer quality** - the AA 17 and the 0.732 rerank MRR were both
  measured with thinking ON. It cannot serve a report (16,000 tokens a minute of
  input, refused locally for free).
- **The pinned lists changed on purpose**: `INPUT_LIMITED` gained the 26B, and
  `REJECTS_THINKING` became `GEMMA_MODELS` + `GEMMA_LEVELS = (MINIMAL, HIGH)` - the
  old test asserted Gemma takes NO level, which was the wrong claim. 4 tests added,
  8 deliberate breaks, all caught.
- **A hazard for Step 2:** it wraps a JSON answer in a ```json code fence even when
  asked for "one JSON object and nothing else". A node that parses its output must
  strip the fence.

#### 15.7 INKLING SMALL: a spent shared cap, no free way around it

429 on 6 of 6. The raw refusal: "Daily limit reached for
thinkingmachines/inkling-small:free via Thinking Machines. Credits don't affect this
cap", X-RateLimit-Limit 1000, Remaining 0, reset 00:00 UTC. **1,000 requests a day
for the whole world, gone by 18:29 UTC.** Checked every route: Cline reaches the same
OpenRouter counter (same `limit_rpd/...-20260730` id, wrapped in an HTTP 500);
OpenRouter directly answers 403 "only available on agentic harnesses"; Routeway,
Requesty and the paid Kilo/OpenRouter ids are PAID ($0.45-$1.87 per million input
tokens). **It cannot be revived for free** - it works in the first hours of a UTC
day, if at all. A 429 costs one 1.1s call, so it stays where its score puts it.

#### 15.8 THE RERANKERS use the OLD numbers, on purpose

Not re-measured, as instructed. They are in `RESULTS.md` section 10 (Flash-Lite
1.3s, Jev 1.2-1.6s, Flash-Lite 3.1 5.3s, Gemma 26B 18.7s, Gemma 31B 22.8s, Cohere
~1s, Voyage 3.8s on a probe of a DIFFERENT model). **The Gemma rerank rows were
measured with thinking on** and may be about 3x too slow for the reason in 15.6.
