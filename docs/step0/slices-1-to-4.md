# Step 0, slices 1 to 4

[Docs home](../README.md)

### Slice 1 — DONE 2026-08-10

Step 0 was five slices, finished one at a time (a six-provider client written in one go has six
places to be wrong at once): (1) tier 1 alone returns text, 2026-08-10 · (2) the fallback loop and 429
backoff over all tiers, 2026-08-12 · (3) dumb retrieval of one hardcoded pair, 2026-08-14 · (4) the
single-pass comparison prompt, 2026-08-17 ([Slice 4 — DONE](#slice-4--done-2026-08-17)) · (5) a bare
FastAPI endpoint, 2026-08-17 ([Slice 5 — DONE](slice-5-and-the-api.md#slice-5--done-2026-08-17)).

`labpilot/llm/` was split by reason to change, not by size: `__init__` (the public API, the only door),
`errors` (`LLMError`), `contracts` (`Attempt`, `LLMResult` — imported by everything, imports nothing),
`defaults`, `_text` (`truncate`), `openai_compatible` (the shared wire format) and `registry` (provider data
and order). Decisions worth keeping:

- **Providers are instances, not subclasses.** OpenRouter, Mistral and Cloudflare differ only in data
  (URL, model, key name). Only Gemini differs in *behaviour*, so only it got its own module.
- **No `base.py` until the second implementation exists.** An interface designed first is a guess; it
  arrived with `gemini.py`, when the real difference was visible.
- **`max_tokens` is an argument of `complete()`**, not a provider field — answer length belongs to the
  task, not the model.
- **The provider stores the *name* of the env var**, never the key; the value is read at call time, so no
  log or `repr` can leak it and CI can inject it.
- Seven failure paths, each with a test: missing key · `RequestException` · non-200 · 200 with a non-JSON
  body · missing or empty `choices` · empty/`null` `content` · empty prompt. The empty prompt raises
  **`ValueError`**, not `LLMError` — a caller's bug must never be swallowed by the fallback loop.
- Tooling landed with it: `pytest.ini`, `ruff.toml` (`E,F,I,UP,B`, line 88), `.pre-commit-config.yaml`,
  `requirements-dev.txt`, CI on every push, and a separate smoke workflow (manual + weekly).

Verified live 2026-08-10: a deliberately broken slug returns **HTTP 400**, not 404 (`... is not a valid model
ID`). The feared "HTTP 200 with an `error` key" did not occur then — re-check if a future provider behaves
differently (it did later: see the 200-with-an-error-body fix in section 15.3 of the Step 2 plan).

### Slice 2 — DONE 2026-08-12

The providers came first, and `gemini.py` first of all: it is the only provider with a different request
*and* response shape, so writing it showed where a shared interface belongs. `GeminiProvider` mirrors
`OpenAICompatibleProvider`; only `_endpoint()`, `_headers()` and `_payload()` differ. Four differences, each
pinned by a test: the model name lives in the **URL** (`{base}/{model}:generateContent`); auth is
`x-goog-api-key`, never `Authorization: Bearer` and never `?key=`; the body is
`contents: [{parts: [{text}]}]` with `maxOutputTokens` inside `generationConfig`; the response is
`candidates[0].content.parts[*].text` plus `finishReason` and `usageMetadata` (camelCase). Extra failure
branches: a **blocked prompt** (`promptFeedback.blockReason`, no `candidates`) and a candidate whose
`content` is `{}` with no `parts`; `AttributeError` is in the caught tuple because `.get()` on a non-dict
raises it where `[...]` raises `TypeError`.

The same day `glm-5-2` and `devstral-2512` (Mistral) and `@cf/openai/gpt-oss-120b` (Cloudflare) landed and
every tier was renumbered onto the benchmark order. Two bugs the renumbering exposed: **reordering `CHAIN`
is not renumbering `tier=`** (the chain read `2, 2, 3, 1, 4, 6`; only an invariant test noticed — `tier` is
now derived from position) and **`DEFAULT_TEMPERATURE` was 0.2, not 0.0** (the repeatability rule had never
been in force; every smoke test until then had been sampling).

### Where to pick up — the rest of slice 2

All four items are DONE. **(1)** The Mistral and Cloudflare providers (2026-08-11). `account_env` carries
Cloudflare's account id into the URL path: one optional field plus `_endpoint()`; a subclass was rejected
(variants that differ only in data are instances), it generalises to Azure/Bedrock, and it stores the
**name**, read at call time. **(2)** `chain.py` (2026-08-12): `LLMClient` walks `CHAIN`, records an
`Attempt` per tier, honours `Retry-After`, skips dead pools and enforces a total time budget.
`AllFreeTiersExhausted` deliberately does **not** subclass `LLMError`, or the loop's own `except LLMError`
would swallow the signal it exists to report. **(3)** `base.py`: `HTTPProvider` owns the template and the
subclasses own `_endpoint` / `_headers` / `_payload` / `_extract_message` / `_usage_summary`, written only
after the second implementation existed. Two abstractions on purpose: `Provider` (a `Protocol` in
`chain.py`, what the chain *requires*) and `HTTPProvider` (an ABC in `base.py`, what providers *share*); an
embedder or reranker inherits neither. **(4)** `context_window` plus the pre-flight `_check_fits`; it does
**not** check tokens-per-minute (a rate, not a per-request size, so it belongs to the backoff) — TPM is what
excluded Groq, a model-selection reason, not a check.

`LLMError` carries `status`, `retry_after` and `reset_at`, filled by `_http.error_from_response`; control flow
branches on those fields, **never on the message string**. `OpenAICompatibleProvider` gained
`account_env` + `_endpoint()`. Four `CHAIN` invariants were pinned then: tiers run 1..N, env vars are
documented in `.env.example`, every provider declares its token limits, and (retired later, see "Why the
adjacency rule was retired") no two adjacent tiers share a key. The old note "promote Mistral if Google is lost"
was superseded by pool-aware skipping.

### Slice 3 — DONE 2026-08-14

Three packages: `labpilot/ingest/` (**permanent**: `Piece`, `Chunk`, three splitters, `chunker.py`),
`labpilot/retrieval/` (**throwaway**: the dumb `select()`, deleted in Step 1) and `labpilot/prompts/`
(`build_context()`); `estimate_tokens` moved to `labpilot/tokens.py` when a second package needed it. The
selector split the budget in half and took chunks from the top of each side: no scoring, scaffolding that was
*supposed* to be bad. Its two flaws were left alone on purpose and became the argument for Step 1: it wasted
budget (14,273 of 20,000 tokens sent on the sample pair, because B filled its half while A needed 4,273) and
it picked by position, not meaning (three of four known bug lines covered by luck, the fourth at line 1146
missed). `tests/unit/test_pipeline.py` runs the real chain with no mocks.

#### The first real answer — measured 2026-08-14

Tier 1 (`gemini-3.6-flash`) answered a bare prompt (context plus one question, no instructions): **10 of 18
findings, 0 hallucinations, about half the line citations correct.** It found the two hardest (pooling the
projected features, and both halves of the scattered stopword fact). Three failures set slice 4's tasks:

1. **It cannot count lines.** Given `lines 579-604` it invented `197` for a line at `205`. A model sees
   text, not line numbers, so the citation rule needed deterministic quoting, not hope.
2. **Its conclusion was false** — the exact trap the fixture was built to set: it subtracted a clean *test*
   F1 (0.851) from a *validation* F1 (0.826, threshold tuned on itself) and declared agreement.
3. **It walked past evidence it was given:** seven of the eight misses were in the text sent to it; only
   one (#9, the threshold leak at line 1146) was the selector's fault.

**Good at *spotting* differences, bad at *judging* them.** Answers are saved in `artifacts/` (git-ignored),
one timestamped file per run with the model, tier, chunk count, failed tiers, the answer and **the exact prompt**
(when an answer is bad the chunks are usually the cause). Two lessons: **a filename typo (`text_context.py`)
hid four tests** — pytest only collects `test_*.py`, so check the *collected* count, not only the passing
count; and `max_tokens` needs ~8,000, not 2,000, because Gemini spends part of the budget thinking.

### Slice 4 — DONE 2026-08-17

**What shipped.** `labpilot/prompts/` is finished for Step 0.

| Module | State |
|---|---|
| `instructions.py` | five templates: `FULL`, `CORE` (frozen baselines) and the lean `REPORT`, `SCAN`, `COMPARE` |
| `citations.py` | deterministic quoting plus `unescape()` for Markdown-escaped quotes |
| `builder.py` | `build_prompt(..., prior=...)`, the channel that carries one pass's findings into the next |
| `context.py`, `_ids.py` | unchanged since slice 3 |

**The measured result, start of slice 4 to end:**

| | before | after |
|---|---|---|
| findings | 10 of 19 (bare prompt) | **13 of 19**, 4 of the 5 that carry the story |
| citations that resolve | reported ~50%, truly unknown | **~99%** |
| the conclusion | wrong — subtracted two incomparable numbers | **correct**, with the bias named and quantified |
| instruction size | grew to 12,620 bytes | **1,997** |

**The four things slice 4 was asked for, and what happened to each:**

1. **Instructions** — delivered, then rebuilt three times. The version that works
   is the smallest one.
2. **A citation mechanism that works** — delivered. Deterministic quoting was
   right from the start; the reported failure rate was our own escaping bug.
3. **A rule about comparing numbers** — delivered, then **found to be wrong** and
   replaced. Requiring the caveat beats banning the comparison.
4. **Real `max_tokens` and the `thinking` field** — delivered. `MEDIUM` beats
   `HIGH`; 64,000 is needed for a full report.

**What slice 4 taught that outlives it.** These are the paragraphs to re-read
before designing any prompt in this project:
[the root cause](prompt-experiments.md#the-root-cause-found-2026-08-17-session-10) ·
[the lean rewrite](prompt-experiments.md#the-lean-rewrite-measured-2026-08-17-session-10) ·
[prompt design rules](prompt-experiments.md#prompt-design-rules-earned-2026-08-17).

**Six tests were added at the close, each verified to fail when its invariant is
broken** — not written to raise a count:

| test | guards |
|---|---|
| `test_side_b_ids_do_not_move_when_side_a_is_absent` | the two-pass contract: `B-25` means one chunk with or without A |
| `test_the_citation_shape_each_template_teaches_is_the_shape_we_parse` | the prompt cannot teach a format our regex will not read |
| `test_the_time_budget_can_outlast_one_slow_call` | `DEFAULT_TOTAL_BUDGET >= DEFAULT_TIMEOUT[1]` — a call allowed longer than the whole budget can never finish |
| three `prior` tests in `test_builder.py` | one pass's findings really reach the next |

**Two limits to state plainly, so nobody re-derives them:**

- **This is one fixture.** Every number in slice 4 comes from `quora_siamese`.
  A second sample pair, in a different domain and language, is the only way to
  tell a general prompt from a quora-shaped one. That belongs in Step 1.
- **`13 of 19` is at or above commercial single-pass code review** (Codex 29%,
  Copilot 34%, Cursor BugBot 41%, Augment 55% with full-codebase context and a
  filtering layer). The remaining gain is **structural**, not verbal: different
  models, and the agent loop at Step 2.
