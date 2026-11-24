# Section 9: function calling measured (M3)

[Docs home](../README.md)

### 9. M3 IS MEASURED — function calling, 2026-09-23

*One request per tier, 40 tiers, on exit `185.209.196.192`, **AS39351 31173
Services AB**, Frankfurt, with Google probed at 200 first. The prompt can only
be answered by calling the tool, so a tier that supports function calling has
no honest way to answer without it.*

```
CALLED         23   a real tool call, with the right argument
IGNORED         1   HTTP 200, no tool_call, no content
REAL "NO"       2   GLM-5.2, both routes
NOT MEASURED   14   503 x5 (transient) · 429 x5 (quota) · 403 x2 (Groq) ·
                    404 x2 (the model is gone)

  503   Gemini 3.8 Flash k1 · 3.7 Flash k1 · 3.5 Flash k1 AND k2 · Gemma k1
  429   Qwen (Kilo, upstream pool) · Inkling (daily) · Mistral Medium ·
        Magistral Small · Devstral 2
  403   both Groq tiers - the exit
  404   both DeepSeek tiers - the free model is gone
```

**Every 503 tier has a twin that CALLED, except `Gemini 3.5 Flash`**, which
503'd on both keys and then timed out at 90s on retry. Its capability is the
one genuine blank in the table.

**And Gemma proved the retry rule twice, in opposite directions, minutes
apart:**

```
first run    key 1  CALLED (80.2s)      key 2  503
second run   key 1  503    (65.6s)      key 2  CALLED (44.0s)
```

Same two tiers, swapped. That is precisely why *"503 -> retry the SAME tier"*
is in the five-way rule, and it is why a 503 in this table is never evidence
about capability.

**All three Mistral tiers were rate-limited together**, so Mistral is
unmeasured here - and it is worth measuring, because Mistral documents
function calling.

**Function calling is close to universal here — 23 of the 24 tiers that gave a
capability answer.** So **D13 stands**, and the hybrid is worth its two code
paths.

#### The assumption in D13 was wrong, and it was mine

D13 said *"Gemma is not a Gemini model and its feature set differs."* Gemma
**calls the tool cleanly**, on both the second Google key and on Requesty. And
every tier a cheap planner call would actually land on supports it:

```
Gemini 3.5 Flash-Lite   x2 keys    CALLED      1,000/day
Gemini 3.1 Flash-Lite   x2 keys    CALLED      1,000/day
Gemma 4 31B             x3 routes  CALLED     28,800/day
```

The only definite refusal is **GLM-5.2**, and it is explicit on both routes:
`404 "No endpoints found that support tool use."`

#### THE RESULT THAT CHANGES HOW D13 IS BUILT

**Kilo's Nemotron 3 Super answered HTTP 200 with no `tool_calls` AND no
`content`.** It accepted the field and silently produced nothing.

That is the shape this project has met before - Cloudflare accepting an
unknown field and ignoring it, OpenRouter silently dropping
`reasoning_effort`. A capability table would record that tier as "supports
tools" and never learn otherwise.

> **DETECT, NEVER CONFIGURE.** Always send `tools`. If the reply carries a
> tool call, use it. If it does not, parse the body as JSON. One path with a
> fallback, not a per-tier flag that goes stale.

That is strictly better than what D13 proposed, and it removes the "capability
flag that has to stay true" cost from the decision.

#### TWO DEFECTS FOUND BY ACCIDENT

**1. `deepseek/deepseek-v4-flash-0731:free` IS GONE.** Confirmed with a plain
call carrying no tools at all:

```
{"error":{"message":"This model is unavailable for free.
           The paid version is available now","code":404}}
```

Kilo answers `404 the requested model does not exist`. **Both DeepSeek tiers
are dead**, and they were added on 2026-09-19 - four days before this probe.

**2. BOTH GROQ TIERS ANSWER 403 FROM THIS EXIT:**

```
{"error":{"message":"Access denied. Please check your network settings."}}
```

Not quota, not tools - Groq is refusing the VPN exit. **The network
precondition only probes Google**, so a Google 200 says nothing about Groq.

> **A capability probe is also a liveness probe.** We went looking for tool
> support and found two dead tiers and a blocked provider. Any sweep across
> the whole chain is worth running for that reason alone.

#### What is still unmeasured, and why

```
Mistral x3     429 rate-limited on all three. Mistral DOCUMENTS function
               calling; we did not measure it
Gemini 3.5 Flash   503 on both keys, then a 90s timeout on retry
Qwen (Kilo)    429 upstream_provider_shared_pool - congestion, not capability
Inkling (Kilo) 429 daily limit reached
Groq x2        403, the exit
```

Every 503 tier has a twin that CALLED, except `Gemini 3.5 Flash`. So the gap
in the table is one model, not a class of them.

The instrument is `scripts/` material and currently lives in the session
scratchpad - **commit it before it is lost**, the same lesson
`score_retrieval.py` and the three lost fusion methods already taught.
