# Full text: LLM Serving — Fallback Chain

[Docs home](../../README.md)

#### THE QUOTA IS PUBLISHED NOWHERE, and that is a real cost to us

Not in the docs, not on any endpoint (`/quota` and `/limits` are 404), not from
a third party. **And Cline sends no rate-limit headers at all** — every response
header was dumped on a 200 and there is no `x-ratelimit-*`, no `Retry-After`.

That matters because
the five-way rule reads exactly
those headers to tell *busy* from *spent* from *not entitled*. On Cline it
cannot, so the chain will retire the pool on the first 429. **This is the one
tier in the project flying blind**, and it is the argument for keeping it at a
position the chain can cheaply skip.

Finding the real limit means calling until it refuses, which spends the thing
being measured. **Not attempted.** The signal that the promotion has ended is
`cost` in the log line turning into a credit deduction.


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

**The local model is now a dev dependency, not a runtime one.** With four remote
rerankers ahead of it, `ms-marco-MiniLM-L-6-v2` would almost never be reached —
and it costs ~120MB resident on a 512MB Render box (see
[Memory budget](../../product/memory-budget.md#memory-budget--render-free-tier-512mb)). Keep it installed for
tests, so integration tests never spend Cohere's monthly bucket, and leave it out
of the deployed container.

Two numbers that were conflated earlier and are not the same thing:
**~22MB** is the int8 weights file on disk; **~120MB** is resident RAM once ONNX
Runtime, the loaded weights and inference buffers are counted. The second number
is an estimate, not a measurement.

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
