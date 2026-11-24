# Constraints

[Docs home](../README.md)

### Constraints
- **OpenRouter free limits — verified 2026-08-10** from their own docs constants
  and from `GET /api/v1/key` on this account (`is_free_tier: true`, $0 spent):

  | Credits purchased, all time | Requests/min | Requests/day |
  |---|---|---|
  | **Less than $10 — us** | **20** | **50** |
  | At least $10 | 20 | 1,000 |

  Three consequences the earlier note missed:
  - **There is also a 20 RPM cap**, not only the daily 50. The backoff must
    respect both.
  - **Limits are global per account.** OpenRouter's docs state plainly that extra
    accounts or API keys do not raise them. Do not try.
  - A **negative credit balance blocks free models too**.

  A single $10 purchase raises the daily cap to 1,000 *permanently* — recorded as
  a fact only; it needs a card, which the no-card rule forbids.
- **You cannot check remaining free quota in advance.** `GET /api/v1/key` reports
  credits *spent*, not free-model requests left, and successful responses carry
  no rate-limit headers. Only a **429** response carries `X-RateLimit-Limit`,
  `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and sometimes `Retry-After`. So
  `chain.py` must be built for *detection*, not prediction — honour `Retry-After`
  when present instead of guessing a delay.
- **A wrong model slug returns HTTP 400**, not 404 (verified 2026-08-10), with a
  readable body: `"... is not a valid model ID"`. That body also contains a
  `user_id` — fine in logs, but the frontend must show a cleaned message.
- OpenRouter free models require the *"Allow free endpoints that train on
  request data"* privacy setting.
- Gemini free tier: prompts may be used to improve Google's products. Grounding
  with Google Search is **not available** on the free tier — fetch papers in our
  own code instead.
- **Gemini thinking tokens — verified 2026-08-11, and this will bite.**
  `maxOutputTokens` budgets **thoughts + answer**, not the answer alone:

  $$
  T_{\text{out}} = T_{\text{think}} + T_{\text{answer}}
  $$

  `gemini-3.5-flash` spent **60 of 64** output tokens thinking, returned
  `content: {}` with no `parts`, and `finishReason: MAX_TOKENS`. Our code
  correctly raised `LLMError: returned an empty answer (MAX_TOKENS)` — but in
  `chain.py` that would fall through to the next tier for no real reason.
  `gemini-3.6-flash` passed on the *same* 64 tokens, so behaviour differs
  **within one model family**. Never assume siblings behave alike.
  Two possible handlings, to be decided in slice 4 when real `max_tokens` values
  are chosen: a minimum floor on Gemini tiers, or
  `generationConfig.thinkingConfig.thinkingBudget` to cap or disable thinking.
  Disabling costs reasoning quality on the hard comparison, which is the one
  thing LabPilot must not lose. Google reports `usageMetadata.thoughtsTokenCount`
  — already in our log line.
- **CLAUDE.md's planned ~200-token "do these even correspond?" call is unsafe on
  a thinking tier.** 200 tokens would be swallowed by thoughts and return
  nothing. Revisit when that call is written.
- Do **not** use `openrouter/free` (the auto-router) — it varies the model
  between calls, which breaks repeatable comparison output.
- **Cerebras is DEAD — verified 2026-08-11.** The API now requires a payment
  method, which the no-card rule forbids. Two sources agree: the dashboard banner
  (*"API access isn't active yet. Add a payment method to start running requests
  and claim $5 in free credits"*) and the API itself:

  ```
  HTTP 402
  {"message":"Payment required to access this resource. Visit your billing tab.",
   "type":"payment_required_error","param":"quota","code":"payment_required"}
  ```

  The key was `ACTIVE` on the dashboard — but that is the *key's* state, not the
  *account's* API access. The 2026-08-08 "no card" note was true for **signup**
  and was never true for the API, because the API had never been called. This is
  the same blind spot as the Google restriction: **an issued API key is not a
  working API.**
- **GLM-5.2 died on Mistral, and there is no free route to it anywhere.**
  *(Verified 2026-08-16, every claim from a provider's own page.)* It answered on
  2026-08-11 and stopped by 2026-08-16 — Mistral changed something, and no error
  message says what. Six routes were checked and **all six are paid**:

  | Route | Status |
  |---|---|
  | Mistral | `limit: 0` — was free, now zero allocation |
  | OpenRouter | `z-ai/glm-5.2` exists, **paid**, no `:free` twin |
  | Z.ai direct | **$1.40 / $4.40** per 1M — paid *at the company that made it* |
  | Z.ai ZCODE CLI | **5-day trial**, then $12.60–$144/month |
  | OpenCode Zen | card required, $1.40/M |
  | Hugging Face | works, but free credit is **$0.10/month** and one report costs **$0.127** |

  Z.ai's free models are **GLM-4.7-Flash / 4.5-Flash / 4.6V-Flash**, never 5.2.

  **This is the blog-source rule proving itself a second time.** A "free routes"
  list named four options; each turned out to be a trial, a credit grant, or a
  paid plan using the word *free*. **Every claim from an official page held;
  every claim from a blog collapsed** — exactly as on 2026-08-08 with Beam,
  Cerebrium and Saturn Cloud.

  **And a new phrase to distrust: "the model is available."** Mistral's admin
  page still lists `glm-5-2` with 1.00 requests/second — while its *tokens per
  minute* is a dash. Requests are granted; tokens are not. **Read every limit a
  provider publishes, not the one that looks reassuring.**
- **Gemini Pro is not on the free tier.** *(Verified 2026-08-16.)*
  `gemini-3.1-pro-preview` and `gemini-pro-latest` both answer `429` with
  *"generate_content_free_tier_requests, **limit: 0**"*, and `gemini-2.5-pro`
  returns `404 — no longer available to new users`. **Same `limit: 0` signal as
  GLM, from a different company** — that phrasing is how providers say *"not on
  your plan"*. Note Google puts it in the **message body** while Mistral puts it
  in a **header**, so `model_is_unavailable` catches Mistral and not Google. Not
  urgent, since no Pro tier is planned.
- ~~**Groq is excluded**~~ **— reversed 2026-08-17. Groq is now tier 12, and the
  original reasoning was right about the number but wrong about the response.**
  Measured on this account:

  ```
  small prompt   200   ok
  27K prompt     413   "Limit 8000, Requested 37770"
  headers        x-ratelimit-limit-requests: 1000
                 x-ratelimit-limit-tokens:   8000
  ```

  **1,000 requests/day** — one of the largest budgets in the project — against
  **8,000 tokens/minute total**, which counts prompt *and* reserved output. So a
  full report is impossible and always will be; even the 32,000-token answer
  alone exceeds the whole budget.

  It earns a place anyway because `context_window = 8_000` makes `_check_fits`
  refuse it **locally**, costing nothing, and because **Step 2's small jobs fit
  easily** — the correspondence gate is ~500 in / 200 out. Groq still offers **no
  embedding models at all**.

  Two corrections worth keeping: the refusal is **413**, not 429 — a status the
  chain treats as "next tier", which is correct. And the old note said "up to
  14,400 RPD"; the measured figure for `gpt-oss-120b` is **1,000**.
- ~~**A 180-second read timeout is too small for a report.**~~ **FIXED — the
  code now reads `DEFAULT_TIMEOUT = (10.0, 600.0)` and
  `DEFAULT_TOTAL_BUDGET = 900.0`.** *(Found 2026-08-17, applied the same day;
  this file went on saying it was owed until 2026-08-26.)* The original failure:
  at 180 s a stuffed report on a thinking model died on `Read timed out`, twice
  in three runs — one measured answer spent 26,678 thought tokens before writing
  a word, and a timeout looks exactly like a dead provider in the logs. **The two
  numbers were raised together, and that is the rule to keep:
  `DEFAULT_TOTAL_BUDGET` must never sit below `DEFAULT_TIMEOUT[1]`**, or a call
  the chain permits can never finish inside the budget the chain enforces.
  `test_the_time_budget_can_outlast_one_slow_call` pins the inequality itself,
  so both numbers may move freely as long as they move together.

  > **A recorded fix is not a fix — and a recorded *applied* fix is not applied
  > either, until the note says so.** Same shape as *"recording a limit is not
  > enforcing it"*, one step later: here the code was right and the file was
  > wrong for nine days, which is the direction nothing ever warns about.
- **Modal is out of the chain entirely.** *(Decided 2026-08-11.)* The $30 is
  reserved for serving the fine-tuned model, which is the job nothing free can do.
  `MODAL_API_KEY` is therefore not needed by `chain.py`, and the chain ends at
  tier 7 with a clean `AllFreeTiersExhausted`.
- **Log which model actually served each request**, for debugging and evaluation.
  With seven tiers this stops being a nice-to-have: without it there is no way to
  tell a healthy chain from one quietly running on tier 6 every time. The same
  fact is also *returned* in `LLMResult.model` — the log is for us, the return
  value is for the UI.
- **Log `finish_reason` too.** `stop` means the model ended on its own; `length`
  means our `max_tokens` cut the answer mid-sentence. Without this field a
  truncated comparison looks like a complete one.
- Implement retry/backoff on 429 before falling through to the next provider.
- **`temperature: 0` on every call.** Comparison output must be repeatable, or a
  real finding cannot be told apart from sampling noise. Caveat: this gives
  greedy decoding, not bit-identical text — Nemotron is MoE on shared hosted
  inference, so expert routing and float reduction order shift with batching.
  Never write an evaluation that assumes exact string equality across runs.
- **Token budget — the real wall is not the context window.** *(Decided
  2026-08-09; the example was updated 2026-08-11 after Cerebras died.)* The
  binding limit is often **tokens per minute**, not context. Groq proves it: 8K
  TPM on a model with a large context window means a 24K-token call can never
  pass, no matter how big the window is. The chain must be sized for its
  *tightest* tier, not its largest. Working numbers: **prompt budget ~20K tokens**
  (instructions + paper + retrieved code) and **`max_tokens` ~4K** — about 24K
  total, which every tier in the current chain accepts.
  - The prompt budget is **our** rule, not the server's. Nothing enforces it but
    our own code: retrieval adds chunks, counts tokens, and stops at the budget.
  - It is an **accuracy** decision as much as a capacity one. A 100K prompt gives
    worse answers than a focused 20K one — attention spreads, and the important
    lines get buried. This is the real reason RAG exists here, not just the wall.
  - Rough sizing without a tokenizer: ~4 characters per token.
- Disclose the data-handling implications in the README.

### Build order — do not wire all six at once

Adding a provider is a small edit once the structure exists — that is the entire
point of `LLMClient`. Get **tier 1 alone** returning text first, then add the
fallback loop, then the remaining tiers. A seven-provider client written in one
go has seven places to be wrong at the same time.

**This session proved the rule the hard way.** On 2026-08-11 an entire session
went to provider research and produced **zero commits** — exactly the failure
CLAUDE.md warns about under Open Risks. The research was necessary (Cerebras had
genuinely died and would have broken `chain.py`), but the lesson stands: verify
what blocks the next commit, then write the commit.

**Still not in the chain:**
- **Lightning AI Model APIs** — *an option only. Not a tier. Do not research
  further until the chain works.* Found 2026-08-09. A separate product from
  Studios, and unrelated to Lightning's GPU credits: a hosted per-token API over
  open and closed models. Their wording: *"Pay by the token. No credit card. Get
  30M free tokens."* Free tier: 15 req/min, 120,000 tokens/min. If a free tier
  is ever needed above Modal, this is the first place to look — but the six-tier
  chain must exist and work before anything is added to it.
- **Nebius Token Factory** — OpenAI-compatible, free credits. Only worth adding
  if yet another separate quota is ever needed. *(Card required for Nebius AI
  Cloud, and the Token Factory signup also asks for a card — treat as blocked.)*

