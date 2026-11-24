# Section 10: slice 0 and the memory budget

[Docs home](../README.md)

### 10. SLICE 0 IS CLOSED, AND THE MEMORY BUDGET WAS 6x WRONG — 2026-09-23

*Measured in the real container, not in a venv, because the 512MB rule is about
a process and an image already existed. Exit `185.209.196.192`, **AS39351
31173 Services AB**, Frankfurt, Google probed at 200 first.*

#### 10.1 SLICE 0 — USE LANGGRAPH

```
langgraph 1.2.12 requires:
  langchain-core · langgraph-checkpoint · langgraph-prebuilt
  langgraph-sdk · pydantic · xxhash
```

**CLAUDE.md's guess was right and it was marked as a guess** - *"the tree above
is from memory, not from an install"*. It named all five and missed only
`xxhash`. **No `torch`, no `numpy`, no `langchain-community`**, so the reject
condition never fires and
`test_no_runtime_requirement_would_blow_the_memory_budget` stays green.

```
idle, WITH langgraph installed   52.39 MiB   (51.61 without -> +0.78)
a fresh process that IMPORTS it  67.65 MB peak, against ~10-12 for bare python
                                 -> about 55 MB, and LESS inside our app
                                    because FastAPI already loads pydantic
```

**The rule was fixed before the measurement: 70 MB use it, above that write the
graph in plain Python.** 55 MB worst case, so **LangGraph ships.**

**And the reducer behaves exactly as taught.** Two nodes, each returning one
finding, with `Annotated[list, operator.add]`:

```
{'findings': ['c1 mismatch', 'c2 match']}
```

Change it to a plain `list` and the second write erases the first, silently.
That is the whole lesson in one runnable line.

**Still unmeasured:** uvicorn with the graph actually imported. That needs
slice 2, because nothing in `labpilot/` imports langgraph yet.

#### 10.2 THE MEMORY ESTIMATE WAS 6x TOO HIGH

CLAUDE.md has carried *"~290-370MB against a hard 512MB ceiling"* since
2026-08-11, **labelled as an estimate and never checked** - the file itself says
*"verify at Step 3 with `docker stats` on a real ingest."*

```
idle                                   51.61 MiB
after an 18-chunk paper                57.63 MiB
after a 928-CHUNK REPOSITORY ingest    74.27 MiB
after a second upload on top of that   73.50 MiB   <- it went DOWN
```

**74 MiB, not 370.** Headroom is **~438 MB**, not ~142.

Three things follow, and the third is the biggest:

1. **Streaming is CONFIRMED, not merely argued.** 928 chunks cost **+22 MiB**,
   and the next upload *reduced* memory - `_records()` yields per batch and the
   GC reclaims it. The rule that ingest must stream is now measured.
2. **The first upload costs ~6 MiB and the second costs nothing.** That 6 MiB is
   `psycopg`, SSL, the embed client and the chunker being imported on first use
   - code, not data. `/health` never touches them.
3. **THE LOCAL RERANKER EXCLUSION SHOULD BE RE-OPENED.** CLAUDE.md keeps
   `ms-marco-MiniLM` (~120MB resident) out of the container *specifically* to
   protect this budget, and calls it *"the correct thing to drop first"*. At 74
   MiB used it would fit with ~300MB to spare - and it is **the only reranker
   that can BATCH**, which is exactly what `verify` needs at one call per claim.
   That decision rested on a number that is wrong by 6x.

**Image size, for completeness:** 204MB -> 442MB on disk. Most of that is
**git**, not langgraph - apt pulls perl and git-man onto slim. Image size is
disk; the 512MB rule is RSS. Do not confuse them, which is what the first
reading of this measurement did.

#### 10.3 DEFECT: THE CONTAINER HAD NO `git`

`POST /artifacts` with `url=` has shipped since slice 7 step 7. In Docker it
answered:

```
{"code":"unreadable_source","message":"git is not installed on this machine"}
```

`python:3.13-slim` carries no git, so **the repository door could never work in
the deployed container** - only on a developer machine. The code behaved
correctly: a typed error with a request id, not a crash.

**Fixed in `docker/Dockerfile`** with an apt layer above the pip install, and
proven: `https://github.com/psf/requests` ingested as **928 chunks** through
the container.

**And a stale line was corrected with it.** CLAUDE.md says the Dockerfile
*"has NEVER been built"*. An image dated 27 days earlier existed the whole
time - which is also why the door's absence went unnoticed: the image predated
slice 7 and had no `/api/v1/artifacts` at all.

> **An unbuilt image and a stale image fail the same way: the thing you are
> running is not the thing you wrote.** The 404 on a shipped endpoint was the
> tell.

#### 10.4 TWO LIMITS WE DO NOT MODEL, AND BOTH BIT TODAY

**TIMEOUT belongs on the provider.** We already model `context_window`,
`max_output_tokens`, `max_input_tokens` and `quota_pool` per provider. Timeout
is global: `DEFAULT_TIMEOUT = (10.0, 600.0)` against a 900s budget.

Token Harbor's failure mode is **a HANG, not an error**. One hung call would
spend **600 of the 900 seconds** on a single dead tier and leave the chain
almost nothing. A 3s cap makes the same tier one of the fastest we have.

> Same shape as `quota_pool`: **a limit that belongs to one provider must be
> modelled on that provider, never averaged into the pipeline.**

**CONCURRENCY is a limit nobody here models at all.** LiteRouter answers

```
403  "[LiteRouter] Too many concurrent requests"
```

and it did so on **sequential** calls - because two earlier requests had timed
out on OUR side while still running on THEIRS, holding the slots. Its published
free plan allows **one concurrent request**.

We model requests-per-day and tokens-per-minute. A chain that fans out - which
is exactly what slice 3's parallel nodes will do - can exceed a concurrency
cap while being far inside every quota we track.

#### 10.5 FIVE GATEWAY PLATFORMS, MEASURED

*Every number below is a live call, not a docs page.*

| platform | free models | quota | measured |
|---|---|---|---|
| **LiteRouter** | **42** | **not published** - no headers, every quota endpoint 404s | **7 of 10 tested work.** Function calling **3 of 3** |
| **OrcaRouter** | 4 + an auto-router alias | **10 rpm / 50 rpd**, from its own `GET /api/free-package/public` | **4 of 4**, 2.4-4.5s |
| **Routeway** | 3 | **5 rpm / 200 rpd**, stated in response headers | DeepSeek **3 of 3** |
| **Token Harbor** | 5 | not published | **8 of 20 rounds** - see below |
| **TeamoRouter** | 3 advertised | advertised 50/day | **0** - `400 "wallet balance is insufficient"` on all three |

**LiteRouter is the strongest find, and three of its models are dead or
unreachable elsewhere:**

```
deepseek-v4-flash-0731:free   11.6s   the EXACT model that died on OpenRouter today
glm-5.3-flash:free             8.1s   OUR TIER 1 - elsewhere only on Cline, blind quota
glm-5.2:free                   7.5s   dead on Mistral (tier_not_allowed), congested on OpenRouter
qwen3.8-27b:free               1.0s   the fastest call measured today
mistral-medium-2508:free       1.5s
gemini-2.5-flash:free          3.7s
deepseek-v4-flash:free         7.7s
```

Failing there: `gpt-oss-120b:free` and `gemma-4-31b-it:free` time out, and
`gemma-4-26b-a4b-it:free` answers `502 "All providers failed. Attempts: 5x.
Last response: Provider returned empty content"`.

**AND ITS FREE ROUTE TAKES A FULL REPORT PROMPT.** A second model claimed the
free 0731 route was capped at a 5,000-token context. Measured:

```
deepseek-v4-flash-0731:free   48,011 real prompt tokens -> 200
glm-5.3-flash:free            27,010 real prompt tokens -> 200
our report prompt             ~15,700 real - fits on BOTH
```

**Wrong by about 10x.** Of that model's five claims about LiteRouter, one was
right (*one concurrent request* - which we had already hit independently), one
is untestable as stated (a *7-second cooldown* hides behind calls that take
7-9s), two were unverified, and one was wrong.

> **Another model's summary is a blog-grade source.** The sources rule already
> says only the provider's own page and the actual flow count. An AI's answer
> is neither.

**OrcaRouter reproduces a finding on a third platform.** `z-ai/glm-5.3-flash`
returns **empty content** without `reasoning.effort`, and `'ok'` with it -
exactly as recorded for Cline. So that is a property of **the model**, not of
Cline, and any new route to GLM-5.3 needs the same setting.

**OrcaRouter also takes a report prompt**: 15,691 real tokens accepted. Note
our `chars/3` estimator called that same text 26,000 - it **over-counts by
~1.66x** against these tokenizers, which is the safe direction and worth
remembering before trusting any budget arithmetic built on it.

#### 10.6 TOKEN HARBOR: WHY "RETRY" IS THE WRONG FIX

Its failure mode is unusual and it took four runs to characterise honestly:

```
single calls, 30s cap     3 of 10       successes all 1.2-1.6s
retry policy, 10 rounds   10 of 10      looked perfect
retry policy, 20 rounds   8 of 20       and the shape is the finding:

    rounds  1-13    1 success out of 13   <- a bad window, minutes long
    rounds 14-20    7 successes out of 7  <- healthy, mostly first try
```

**Failures are TIME-CORRELATED, not independent.** During a bad window six
retries fail exactly as surely as one - rounds 1-13 spent **78 calls for 1
answer**. The 10/10 run simply landed inside a healthy window.

So the independent-failure arithmetic (*"4 tries gives 87%"*) is fiction here,
and **more retries is the wrong lever**. The right one is the mechanism we
already have for a spent quota:

```
1 try · ~3s cap · on failure mark the tier dead for a few minutes
```

`dead_pools` in `llm/chain.py` already does exactly this shape. A 2s cap was
considered and rejected: real answers were measured at 2.86, 3.21, 3.99 and
4.44s, so 2s would discard about one success in five.

#### 10.7 THREE MORE DECISIONS

| # | decision |
|---|---|
| **D14** | **Jargon and acronym expansion is a NAMED GAP.** The research listed three cases where professionals rewrite a query; D5 covers multi-turn and D2 covers decomposition, and **nothing covers the third**. It is the one that fits us worst: a claim from A is written in the paper's words (*"attention pooling over hidden states"*) and B is written in the programmer's (`_attn_pool`, `CLIP_NORM`). BM25 and the reranker compensate by accident; nothing bridges the two vocabularies on purpose |
| **D15** | **SLICE 2 MUST SHIP A CHECKPOINTER AND A `thread_id`, not only nodes and edges.** LabPilot is a CHAT, and no slice built conversation state. D5 would have a node with nothing to read, and CLAUDE.md's own UI example - *"now compare **it** with my code"* - cannot work without it. LangGraph's checkpointer is the mechanism: `compile(checkpointer=...)` plus `config={"configurable": {"thread_id": ...}}` makes turn 2 read turn 1's state. **Refined 2026-10-06 in [section 17](17a-chat-memory.md#17-chat-memory-storage-and-cleanup--decided-2026-10-06)** |
| **D16** | **Adding a gateway is not just a registry entry.** Each new platform needs its provider wiring, its place in `CHAIN` argued on measured capability, its env var in `.env.example` AND in `smoke.yaml` (which `test_every_chain_env_var_is_mapped_in_the_smoke_workflow` enforces), and a liveness case. `test_every_gateway_tier_is_free` already exists for exactly this class of drift |

#### 10.8 THE METHOD LESSON, EARNED THREE TIMES IN ONE SESSION

Three times today a single call was read as a verdict, and three times the
larger sample overturned it:

```
Qwen (Kilo) 429            "overloaded"       -> works on retry, both accounts
Routeway DeepSeek 429      "unusable"         -> 3 of 3 on retry
Token Harbor              "works with curl"   -> one lucky sample; curl hangs too
Token Harbor              "100% with retry"   -> 40% over twice as many rounds
```

This file already carries the rule in another form - *a fixture may REJECT,
never CONFIRM* - and it applies to providers exactly as it applies to corpora.

> **A single success and a single failure are both samples of one.** Before
> writing a provider verdict, run it enough times to see a rate, and print the
> denominator beside it.
