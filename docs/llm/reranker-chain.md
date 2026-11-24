# Chain 3: the rerankers

[Docs home](../README.md)

### Chain 3 — Reranker (true fallback)

*Rewritten 2026-09-11 on MEASUREMENT. The old order was argued from quota
shape; every row below was scored on quora at a 30-document window against
vector alone's MRR of **0.608**.*

| # | Model | Provider | MRR quora | MRR geo | Budget | Kind |
|---|---|---|---|---|---|---|
| 1 | **`gemini-3.5-flash-lite`** | Google | **0.799** | 0.681 | 500/day | LLM, listwise |
| **2** | **`typesafe/jev-1.13`** | **OpenRouter** | **0.770** | **0.712** | **PAID, $0.042/M in** | **decision model, listwise** |
| 3 | **`gemini-3.1-flash-lite`** | Google | **0.745** | — | its own 500/day | LLM, listwise |
| 4 | **`gemma-4-26b-a4b-it`** | Google | **0.732** | — | its own 14,400/day | LLM, listwise, MoE |
| 5 | **`gemma-4-31b-it`** | Google | **0.732** | — | 14,400/day | LLM, listwise |
| **2b** | **`jev-1.13.0` via Netlify** | **Netlify AI Gateway** | same model | same model | **FREE, 300 credits/month** | decision model — the fallback, added 2026-09-29 |
| 6 | **`rerank-v4.0-fast`** | Cohere | 0.669 | 0.621 | 1,000/**month** | cross-encoder |
| 7 | `rerank-3` | Voyage | *unmeasured* | — | 200M once · 3 RPM | cross-encoder |
| 8 | `rerank-3-lite` | Voyage | 0.725 | — | its own 3 RPM | cross-encoder |
| — | *vector alone* | — | *0.608* | *0.526* | — | *the line to beat* |
| 9 | **skip** | — | — | — | — | degraded, still works |

**Jev is tier 2 as a MODEL and tier 3 in the assembled chain**, because every
Google tier is built on BOTH accounts — so assembled slot 2 is flash-lite's
second free 500/day. A billed tier there would spend money while a free
allowance sat unused. Twelve assembled tiers now; see
[Jev, the decision model](jev.md#jev--the-decision-model-and-the-first-paid-tier-2026-09-19).

**REORDERED AND SHORTENED 2026-09-19 — read this table as the SHIPPED chain.**
Each of rows 1-4 is built on BOTH Google accounts, so `api/reranking.py` assembles
**eleven** tiers with Cohere at 9. Two changes, both on prior evidence, because
the v3 re-measurement was killed — see `docs/slice8v3/DECISIONS.md` §29.

**Four things to read carefully.**

**The top four are LLMs, and they beat every purpose-built cross-encoder.**
Listwise: one call ranks all documents, so 30 documents cost 1 call and not 30.
Google's quota is per MODEL, so those four are **four independent buckets** —
1,000 + 28,800 calls a day with no shared ceiling.

**`bge-reranker-base` IS DELETED — 2026-09-19.** It measured **worse than not
reranking** and was kept pending a re-check, on the argument that one saturated
corpus is thin evidence and its ~2,840/day budget cannot run out. v1's F6 named
the condition for removal — *"worse than not reranking on three corpora, two
languages, three domains"* — **the condition was met and the re-check will not
happen.** The chain already ends in `skip()`, which is strictly better than a
tier measured below vector alone. `KNOWN_WORSE_THAN_NOT_RERANKING` is now EMPTY,
so putting ANY such tier back breaks the build.

**COHERE MOVED ABOVE VOYAGE.** Slice 6 put it below on ONE corpus — `quora`, the
saturated 82-chunk fixture — at 0.669 against rerank-3-lite's 0.725. v2 added
three more corpora and that did not reproduce: Cohere is the only reranker
measured that has **never hurt a corpus**, and it rescues `gson` — flash-lite's
worst case — by 5.8 queries. `rerank-3`, which sat above it, has never been
scored anywhere. It stays BEHIND all eight LLM tiers, which is the budget half of
the same finding: 1,000 calls a MONTH against flash-lite's 1,000 a day.

**`rerank-3` leads `rerank-3-lite` on a single-pair probe** (0.8594 to 0.8516)
and is otherwise unmeasured — a reason to try it first, not evidence.

**Two tiers were DROPPED**, both measured below vector alone:
`ministral-3b-2512` (0.440) and the local ONNX cross-encoder (0.472).

### The LLM tiers cannot live in `rerank/`, and the fix is a callable

An LLM reranker needs `llm/`. Both are **adapters**, and `test_architecture`
forbids an adapter importing another adapter — two adapters that know each
other's types are welded together and neither can be replaced.

**`rerank/` had already solved this shape once.** It cannot see `SearchHit`
either, so it takes plain strings and lets the caller translate. Same answer:
`LLMReranker` takes **`complete(prompt, max_tokens) -> str`**, not a provider.

```python
LLMReranker(
    complete=lambda p, n: GEMINI_3_5_FLASH_LITE.complete(p, max_tokens=n).text,
    name="Gemini 3.5 Flash-Lite",
    model="gemini-3.5-flash-lite",
)
```

The coupling lives at the call site, in a layer allowed to see both. So the
four LLM tiers are **not** in `RERANK_CHAIN` — they are `LLM_RERANK_ORDER`,
data in measured order, and **slice 7 assembles the real chain at the entry
layer**: `rerank(query, docs, chain=(*llm_tiers, *RERANK_CHAIN))`.

> **A layering rule that blocks a feature is usually pointing at the wrong
> shape, not at the wrong rule.** The callable is better than the import would
> have been: it makes the reranker testable with no provider at all.

### How a Gemini model must be configured for ranking

Two settings, both measured, and together worth more than the gap between
flash-lite and Cohere's purpose-built cross-encoder:

```python
{
    "thinking": None,
    "generation_config": {
        "responseMimeType": "application/json",
        "responseSchema": {"type": "ARRAY", "items": {"type": "INTEGER"}},
    },
}
```

- **`thinking=None`** — MEDIUM costs 3.88 s and 930 thought tokens against
  1.28 s and 0, for an **identical** answer. Every Gemini tier ships MEDIUM.
- **A JSON schema** — gemma 45.5 s → 14.4 s, and the reply stops being prose
  wrapped around an answer.

`GeminiProvider.generation_config` carries it, the Gemini twin of
`OpenAICompatibleProvider.extra_body`. Step 2's claim extraction needs the same
field to get parseable output.

**LLM-as-reranker is no longer rejected outright.** *(Position changed
2026-08-11.)* The old objection was that it spends a generation call — the
scarcest resource. That does not hold for `ministral-3b-2512`: it sits on
Mistral's quota, which is separate from OpenRouter and Google, and it is the
fastest, cheapest model on that platform. It is still worse than a purpose-built
cross-encoder, which is why it is tier 4 and not tier 1.
*(UPDATE 2026-09-19: `ministral-3b-2512` measured MRR 0.440 and the local ONNX
cross-encoder 0.472, both below vector alone (0.608), so both were DROPPED from the
chain; the LLM tiers that lead chain 3 now are Gemini Flash-Lite and Gemma.)*

**The local model is now a dev dependency, not a runtime one.** With four remote
rerankers ahead of it, `ms-marco-MiniLM-L-6-v2` would almost never be reached —
and it costs ~120MB resident on a 512MB Render box (see
[Memory budget](../product/memory-budget.md#memory-budget--render-free-tier-512mb)). Keep it installed for
tests, so integration tests never spend Cohere's monthly bucket, and leave it out
of the deployed container.

Two numbers that were conflated earlier and are not the same thing:
**~22MB** is the int8 weights file on disk; **~120MB** is resident RAM once ONNX
Runtime, the loaded weights and inference buffers are counted. The second number
is an estimate, not a measurement. *(UPDATE 2026-09-23: the 512MB ceiling it was
weighed against turned out ~6x emptier than assumed, see the corrected Memory
budget; the dev-dependency decision stands, the reason is weaker.)*

**Rerankers that do not exist anywhere free:** Groq (chat/Whisper/TTS/vision
only), llm7.io (chat/video/image only), Mistral (zero matches in `/v1/models`).
Jina offers 1M free tokens ≈ 40 calls — too small to be a tier.

**Cohere auto-chunks documents longer than 510 tokens**, which silently multiplies
the billed document count. Keep chunks under that.

**Live progress events — Step 3, not Step 0.** For the UI trace ("Asking
Nemotron 3 Ultra… failed 429 → asking Gemini 3.6 Flash"), `LLMClient` takes an
optional callback and emits one small fixed event before and after each tier.
FastAPI forwards them to the browser over SSE. This does not break the rule
above: *emitting a fact is not talking to the user.* `LLMClient` reports; the
caller decides what to display, and the caller is the only place that may *ask*
anything. Keep the event shape small and provider-neutral, for the same reason
as `LLMResult`. Word the trace honestly — at that moment the code is waiting on
HTTP, so "Asking Nemotron…" is true and "Nemotron is thinking…" is not.

**Modal's real job is the fine-tuned model** (Gemma 4 open weights + our LoRA
adapter). Tier 6 is a borrowed side-use of the same $30, not what the credit is
for. If the two ever compete, the fine-tuned demo wins.
