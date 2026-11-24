# The three chains

[Docs home](../README.md)

## LLM Serving — Fallback Chain

All model access goes through a single `LLMClient` interface (one method,
`generate(prompt) -> LLMResult`). **Nothing else in the codebase talks to a
provider directly.** This is deliberate: free endpoints appear and disappear
constantly, so a provider change must be a one-file edit, not a refactor.

`LLMResult` carries four fields: `text` (never empty — an empty answer is a
*failure*, not an answer), `model`, `tier`, and `attempts` (what each failed
tier returned). Decided 2026-08-09: the frontend must show which model answered
and which ones failed first, so model identity has to cross the seam — reaching
the log file is not enough.

**Token usage — logged now, returned later.** *(Decided 2026-08-10.)* Every
provider reports it (`usage.prompt_tokens` on the OpenAI shape,
`usageMetadata.promptTokenCount` on Gemini), so it passes the six-provider test
and belongs in `LLMResult` **eventually**. Today it goes only to `logger.info`,
because nothing reads it yet and a returned field nobody reads is dead code.
Logging it already buys two things: real token counts to check the `chars / 3`
estimate against, and visibility on per-minute token caps, where tokens bind
before request count does — the limit that excluded Groq entirely.

Promote it to `prompt_tokens` / `completion_tokens` on `LLMResult` the moment
the UI or the budget validator needs the number — the log cannot cross the seam
to the frontend, only the return value can.

**The test for anything new in this interface: it must be true for every
provider in the chain.** Model identity and failure reasons pass — every provider
reports them. Streaming does not, so it stays out.

### The three chains — restructured 2026-08-11

LabPilot needs **three** model stages, and they are not the same kind of chain.
The difference comes from one question: *does this stage write state that later
calls must match?*

| Stage | Writes state? | Kind of chain | Failure is |
|---|---|---|---|
| **Generator** | No — text is text | true fallback chain | **fatal** |
| **Reranker** | No — scores sort one list, then are discarded | true fallback chain | **degraded**, not fatal |
| **Embedder** | **Yes — vectors live in pgvector** | **migration, not fallback** | **fatal** |

Two embedders never mix. A query vector and a stored vector must come from the
same model, or cosine similarity is noise:

$$
\cos\big(E_A(q),\, E_B(d)\big) = \text{meaningless}
$$

A reranker's scores never meet across models — each request sorts its own 50
chunks and forgets them — so switching is free. That asymmetry is the whole
reason the three chains are shaped differently.

### Chain 1 — Generator (true fallback)

Ordered by **measured capability**, not by quota and not by vendor claims.
Two independent sources were used (see [Model ranking](model-ranking.md#model-ranking--how-the-order-was-decided-2026-08-11)).

*Rebuilt 2026-08-17, and **regenerated from `CHAIN` itself on 2026-09-13** —
**twenty-three tiers**. The table below had been left at the fifteen-tier shape
and was therefore already wrong before Cline arrived: it was missing every
`(key 2)` twin added on 2026-09-11. Every row was proven live before it was
added.*

**The numbers are POSITIONS, derived by `_ordered()`, never typed.** Read this
table by model name; a tier index in this file has gone stale three times now.

> **⚠ OUT OF DATE (2026-10-06): this table lists 40 tiers, but `CHAIN` has 56.** Read `labpilot/llm/registry.py` for the real order. Tier numbers here have been wrong before.

| # | Model | Provider | AA v4.3 | Code Arena | Note |
|---|---|---|---|---|---|
| 1 | GLM-5.3 Flash (Cline) | Cline | 42 | 1607 (#17) | 1,310,720 ctx / 131,072 out |
| 2 | Gemini 3.8 Flash | Google | 41 | 1568 (#23) | 1,048,576 ctx / 65,536 out |
| 3 | Gemini 3.8 Flash (key 2) | Google (Key 2) | 41 | 1568 (#23) | 1,048,576 ctx / 65,536 out |
| 4 | Gemini 3.7 Flash | Google | 39 | — | 1,048,576 ctx / 65,536 out |
| 5 | Gemini 3.7 Flash (key 2) | Google (Key 2) | 39 | — | 1,048,576 ctx / 65,536 out |
| 6 | DeepSeek V4 Flash (Kilo) | Kilo | 35 | 1580 (#22) | 1,048,576 ctx / 393,216 out |
| 7 | DeepSeek V4 Flash | Openrouter | 35 | 1580 (#22) | 1,048,576 ctx / 393,216 out |
| 8 | Qwen3.8 27B (Kilo) | Kilo | 34 | 1593 (#18) | 262,144 ctx / 235,929 out |
| 9 | Qwen3.8 27B | Cloudflare | 34 | 1593 (#18) | 262,144 ctx / 262,144 out |
| 10 | Qwen3.8 27B (Groq) | Groq | 34 | 1593 (#18) | 8,000 ctx / 8,000 out |
| 11 | Gemini 3.6 Flash | Google | 34 | 1537 (#32) | 1,048,576 ctx / 65,536 out |
| 12 | Gemini 3.6 Flash (key 2) | Google (Key 2) | 34 | 1537 (#32) | 1,048,576 ctx / 65,536 out |
| 13 | Gemini 3.5 Flash | Google | 33 | 1500 (#44) | 1,048,576 ctx / 65,536 out |
| 14 | Gemini 3.5 Flash (key 2) | Google (Key 2) | 33 | 1500 (#44) | 1,048,576 ctx / 65,536 out |
| 15 | GLM-5.2 (Kilo) | Kilo | 34 | 1592 (#19) | 32,768 ctx / 29,491 out |
| 16 | GLM-5.2 | Openrouter | 34 | 1592 (#19) | 32,768 ctx / 29,491 out |
| 17 | Laguna S 2.1 (Cline) | Cline | — | — | 262,144 ctx / 32,768 out |
| 18 | Laguna S 2.1 (Kilo) | Kilo | — | — | 262,144 ctx / 32,768 out |
| 19 | Nemotron 3 Ultra (Kilo) | Kilo | — | — | 1,000,000 ctx / 65,536 out |
| 20 | Nemotron 3 Ultra | Openrouter | — | — | 1,000,000 ctx / 65,536 out |
| 21 | Nemotron 3 Ultra (Requesty) | Requesty | — | — | 1,000,000 ctx / 65,536 out |
| 22 | Inkling Small (Kilo) | Kilo | 26 | 1407 (#73) | 1,048,576 ctx / 131,072 out |
| 23 | Gemini 3.5 Flash-Lite | Google | 23 | — | 1,048,576 ctx / 65,536 out |
| 24 | Gemini 3.5 Flash-Lite (key 2) | Google (Key 2) | 23 | — | 1,048,576 ctx / 65,536 out |
| 25 | Mistral Medium | Mistral | — | — | 262,144 ctx / 262,144 out |
| 26 | Step 3.7 Flash (Kilo) | Kilo | 19 | — | 262,144 ctx / 65,536 out |
| 27 | Muse Glimmer 30B (Requesty) | Requesty | 18 | — | 262,144 ctx / 32,768 out |
| 28 | Gemma 4 31B | Google | 15 | — | 262,144 ctx / 32,768 out |
| 29 | Gemma 4 31B (key 2) | Google (Key 2) | 15 | — | 262,144 ctx / 32,768 out |
| 30 | Gemma 4 31B (Requesty) | Requesty | 15 | — | 262,144 ctx / 32,768 out |
| 31 | North Mini Code (Kilo) | Kilo | — | — | 256,000 ctx / 64,000 out |
| 32 | North Mini Code | Openrouter | — | — | 256,000 ctx / 64,000 out |
| 33 | Nemotron 3 Super (Kilo) | Kilo | — | — | 262,144 ctx / 235,929 out |
| 34 | Nemotron 3 Super | Openrouter | — | — | 262,144 ctx / 262,144 out |
| 35 | GPT-OSS 120B | Cloudflare | — | — | 128,000 ctx / 128,000 out |
| 36 | GPT-OSS 120B (Groq) | Groq | — | — | 8,000 ctx / 8,000 out |
| 37 | Magistral Small | Mistral | — | — | 262,144 ctx / 262,144 out |
| 38 | Devstral 2 | Mistral | — | — | 262,144 ctx / 16,384 out |
| 39 | Gemini 3.1 Flash-Lite | Google | — | — | 1,048,576 ctx / 65,536 out |
| 40 | Gemini 3.1 Flash-Lite (key 2) | Google (Key 2) | — | — | 1,048,576 ctx / 65,536 out |

† **AA INDEX v4.3, RE-READ 2026-09-19, AND IT IS NOT THE OLD COLUMN.** Every
number marked † comes from Artificial Analysis's own v4.3 evaluations, read
from their per-model pages. **The un-marked rows are from an older index
version and MUST NOT be compared with them.** The gap is not small: this file
recorded Flash-Lite at **37.4** and v4.3 scores it **23**; Gemma 4 31B was
**29.7** and is now **15**. LMArena numbers in this table are now **Code
Arena** Elo, which is the leaderboard relevant to what this project does.

> **An index is a measuring stick, and measuring sticks get replaced.** Two
> scores from different versions look comparable and are not. Re-score the
> whole column or mark which rows are which — never mix them silently.

⏸ = alive but **unreachable today**, because a report prompt exceeds its limit.
Each is refused *locally* by `_check_fits`, so it costs no request and no time —
see [Input limits](quotas-and-pools.md#two-kinds-of-limit-and-they-are-not-the-same-thing).

**The ordering rule is capability, full stop.** An earlier draft put the ⏸ tiers
at the back and `gemini-3.1-flash-lite` at tier 8 "because it has 500/day". Both
were wrong, and the user rejected them:

- the quota argument was **already spent** at tier 6, which supplies the volume
- and once `max_input_tokens` made a blocked tier free, there was **no cost left
  to avoid**, so nothing justified demoting a stronger model

> **Order by power. Let the limit fields handle reachability.** A tier that
> cannot run costs nothing; a tier ranked below its ability costs quality on
> every call.

**Three tiers are ordered on judgement, not evidence** — Magistral Small,
Gemini 3.1 Flash-Lite, and the relative position of the two GPT-OSS hosts.
Neither of the first two appears on AA or LMArena. **Settle them by running the
fixture, not by arguing.**

**GLM-5.2 is kept at tier 4 on purpose.** With the `limit: 0` rule, a dead tier
costs one request, no retry, and no damage to its pool. If Mistral restores the
allocation it starts working **with no code change**, because the chain reads the
live header rather than a note in this file. The smoke suite marks it
`xfail(strict=False)`, so a revival shows up as **XPASS** instead of silence.

**Two reasoning models were sitting unused the whole time.** `/v1/models` on
Mistral reports a `capabilities.reasoning` flag, and it was never read.

**Two reasoning models were sitting unused the whole time.** `/v1/models` on
Mistral reports a `capabilities.reasoning` flag, and it was never read. CLAUDE.md
had judged Mistral solely on `mistral-large-3` (AA 16, rejected) and concluded
Mistral had nothing strong. That conclusion was about **one model**, not about the
platform. **When a provider is dismissed, record which model was tested — the
next reader will otherwise inherit the conclusion without the evidence.**

**Neither new model has a benchmark score.** Their order (Medium above Magistral)
is a guess from name and size, and is explicitly *not* measured. Settle it on the
fixture before trusting it.

**Modal is no longer in the chain.** *(Decided 2026-08-11.)* Its $30 is reserved
entirely for serving the fine-tuned model. That removes the user-consent gate:
`AllFreeTiersExhausted` is now a plain terminal error, and `LLMClient` never
needs to ask the user anything.

Design consequence, unchanged: `generate` cannot always return an `LLMResult`.
It reports *"all free tiers exhausted"* as a distinct exception,
`AllFreeTiersExhausted`, separate from the per-tier `LLMError` that the fallback
loop swallows — or the loop's own `except LLMError` would swallow the signal it
needs to report.

**Tiers 5 and 6 are the code-*writing* specialists.** They rank low for general
reasoning, which is LabPilot's main job, but they are the right models when the
user asks for a snippet. Neither appears on LMArena at all — because LMArena
measures conversational preference and these are agentic coding models, not chat
models. At Step 2, LangGraph should **route** that sub-task to them directly
rather than walking the chain.

**Why Devstral sits above the higher-scoring North Mini Code.** *(Decided
2026-08-11, after a test caught it.)* Ordering strictly by capability put
Nemotron (t4) and North Mini Code (t5) adjacent, and **both draw on OpenRouter's
one 50/day pool** — so once the account cap is spent, tier 5 fails for the same
reason tier 4 did, and the chain wastes an attempt. Swapping 5 and 6 makes the
pools alternate:

```
GOOGLE · MISTRAL · GOOGLE · OPENROUTER · MISTRAL · OPENROUTER
```

The trade is a frequent small gain against a rare small loss: adjacency costs an
attempt *every day* once OpenRouter is spent, while the capability difference
only matters when four tiers above have already failed. Pool-aware 429 skipping
would fix this properly, but it does not exist yet — it is planned for
`chain.py`. When it lands, the swap costs nothing and can stay.

~~The invariant is pinned by `test_no_two_adjacent_tiers_share_an_api_key`.~~
**Retired 2026-08-16** — pool-aware skipping made adjacency free. See
[Why the adjacency rule was retired](quotas-and-pools.md#why-the-adjacency-rule-was-retired--2026-08-16).
The reasoning above is kept because it explains why the *pool*, not the provider
name, is the thing that runs out.
