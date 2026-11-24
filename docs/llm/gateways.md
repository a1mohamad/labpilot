# Gateways and added models

[Docs home](../README.md)

### Cline — the eighth platform, and the free tier that costs no credits (2026-09-13)

*Investigated at the user's request, tested against the real API with the user's
own key, and then built. `z-ai/glm-5.3-flash` now leads chain 1.*

**The headline: Cline's free models do not consume credits at all.** This was
proven with a control, because "the balance did not move" on its own could just
mean billing is slow.

| call | `costUsd` recorded | **`creditsUsed`** | balance |
|---|---|---|---|
| `glm-5.3-flash`, 1,717 tokens | 84,625 | **0** | 500000 → 500000 |
| `glm-5.3-flash`, 1,592 tokens | 78,375 | **0** | 500000 → 500000 |
| `laguna-s-2.1:free`, 52 tokens | 0 | **0** | 500000 → 500000 |
| **control — `mistral-small-3.2-24b` (paid), 13 tokens** | 147 | **1** | 500000 → **499999** |

The control deducted **instantly**, so billing is not delayed — free models are
genuinely exempt. Cline records what the call *would* have cost and charges
nothing. Read the ledger at `GET /api/v1/users/{userId}/usages`; the balance is
at `GET /api/v1/users/{userId}/balance`, in micro-credits (500000 = 0.5).

> **A balance that does not move is not evidence until a paid control moves
> it.** Two explanations fit "nothing was charged" — exempt, or delayed — and
> only the control separates them.

#### Only 2 of the 6 free models answer the API

| model | API | result |
|---|---|---|
| **`z-ai/glm-5.3-flash`** | ✅ 200 | **built — tier 1** |
| `poolside/laguna-s-2.1:free` | ✅ 200 | reachable, **not built** — unmeasured quality |
| `cline-free/muse-spark-1.3-contributor` | ❌ 403 | *"only available via Cline product surfaces"* |
| `cline-free/solar-pro4` | ❌ 403 | same |
| `cline-free/longcat-2.0` | ❌ 403 | same |
| `deepseek/deepseek-v4-flash` | ❌ 403 | same |

Cline's docs say free models are not available through the API at all. That is
**half right**: the gate is **per model**, and it is not the `cline-free/`
namespace either — `deepseek/deepseek-v4-flash` is an ordinary catalogue id and
is still blocked, while `glm-5.3-flash` is on the free list and answers.

**The free roster rotates and is discovered here, not in the docs:**

```
https://api.cline.bot/api/v1/ai/cline/recommended-models   -> recommended / free / clinePass / clineCloud
https://api.cline.bot/api/v1/ai/cline/models               -> the full catalogue
```

Both are **public, no key needed**. The documentation page names no models at
all, and the screenshots on it were already stale — they showed
`cline-free/glm-5.2` and `stepfun/step-3.7-flash`, neither of which is on the
live list.

#### `api/v1/models` is OpenRouter's catalogue, not Cline's

445 models from Cline, 445 from OpenRouter, **100% overlap, zero difference**.
Cline's own docs admit the convention — *"the same convention used by
OpenRouter"* — and its usage ledger records
`aiInferenceProviderName: "openrouter"`. Neither `cline-free/` nor
`cline-pass/` appears in that list.

> **When a provider's catalogue is exactly another provider's catalogue, it is
> a mirror.** Counting the rows took one command and settled what an hour of
> reading could not.

#### THE QUOTA IS PUBLISHED NOWHERE, and that is a real cost to us

Not in the docs, not on any endpoint (`/quota` and `/limits` are 404), not from
a third party. **And Cline sends no rate-limit headers at all** — every response
header was dumped on a 200 and there is no `x-ratelimit-*`, no `Retry-After`.

That matters because
[the five-way rule](failure-rules-and-limits.md#how-the-chain-decides--the-six-way-rule) reads exactly
those headers to tell *busy* from *spent* from *not entitled*. On Cline it
cannot, so the chain will retire the pool on the first 429. **This is the one
tier in the project flying blind**, and it is the argument for keeping it at a
position the chain can cheaply skip.

Finding the real limit means calling until it refuses, which spends the thing
being measured. **Not attempted.** The signal that the promotion has ended is
`cost` in the log line turning into a credit deduction.

#### `reasoning.effort` is what makes the tier work, and it works backwards

Five runs each, one prompt, `max_tokens=1500`:

```
no reasoning field        2 of 5 succeeded      ~1,200 reasoning tokens
reasoning.effort = high   5 of 5 succeeded       17-60 reasoning tokens
```

Without it `glm-5.3-flash` spends its whole budget thinking and returns empty
content, which Cline reports as **its own HTTP 500 `empty response content`** —
not a 400, not a `finish_reason`, so nothing downstream can diagnose it.

**Note the direction: an explicit effort CAPS the reasoning on this model
rather than raising it.** That is why it fixes the failure. It is the same
shape as slice 6's `thinking=None` on flash-lite — a reasoning knob whose
useful setting is the *low* one — and the third time in this project that a
thinking control has behaved opposite to its name.

Cline **silently ignores unknown fields** (an invented `zzz_nonsense` returned
200), so a wrong spelling here would fail silently. The OpenRouter spelling is
right because Cline routes through OpenRouter.

#### The response is NOT the OpenAI shape

```json
{"data": {"choices": [...], "usage": {...}}, "success": true}
```

`OpenAICompatibleProvider._extract_message` reads `body["choices"][0]` and
raises *"unexpected response shape"* on every call. So `ClineProvider`
subclasses it and overrides only the two **reading** methods; the request side
is standard OpenAI and is reused unaltered.

**One Python trap worth keeping:** the providers are `@dataclass(slots=True)`,
and that decorator builds a **new class object**. Zero-argument `super()` then
resolves through a `__class__` cell pointing at a class no longer in the MRO.
`ClineProvider` calls `OpenAICompatibleProvider._extract_message(self, ...)`
explicitly for that reason.

#### Why it leads the chain

Every Google Flash model is **20 requests a day**. A free tier in front of them
spends nothing we are short of. That is the whole argument, and it is the same
one that put Flash-Lite ahead of stronger models for volume.

**What is NOT claimed: that it is the best model here.** It has no AA score and
no LMArena rank, so its position is *not* the measured-capability ordering the
rest of the table uses — it is a budget decision, and it is the user's call,
recorded as such. Slice 8 can score it on the real fixture.

#### Laguna S 2.1 is tier 9, and the placement is measured — 2026-09-13

*Added after the user refused a one-benchmark decision: "you have only terminal
benchmark? we need more benchmark to compare!!!!" That objection was right and
it moved the answer — on Terminal-Bench alone, Gemini 3.6 Flash beats Laguna;
on SWE-Bench Pro the reverse is true, and the two cancel.*

**Head-to-head, counting only where both models appear on a leaderboard:**

| Laguna vs | Record | Evidence |
|---|---|---|
| Nemotron 3 Ultra (was t9) | **2–0** | TB 0.702/0.564 · SWE-ML 0.785/0.677 |
| Gemini 3.5 Flash-Lite (t11) | **2–0** | TB 0.702/0.540 · SWE-Pro 0.594/0.542 |
| Gemini 3.6 Flash (t4) | 1–1 | loses TB 0.780, wins SWE-Pro 0.587 |
| Gemini 3.5 Flash (t6) | 1–1 | wins SWE-Pro 0.551, loses Toolathlon 0.565 |
| GLM-5.2 (t8) | 1–2 | loses TB and SWE-Pro, wins Toolathlon |
| **GLM-5.3 Flash (t1)** | **0–2** | TB 0.843 · Toolathlon 0.784 |

It sits **exactly between tier 8 and the old tier 9**, so it becomes tier 9 and
Nemotron 3 Ultra moves to 10. This is the project's own rule applied — *judge a
method by how many independent ways it was shown better, never by its best
single number.*

**It is NOT ranked the way the rest of the table is.** Every other row is
ordered on the AA Intelligence Index plus LMArena. Laguna appears on **neither**
— nor on GPQA or MMLU. It is a pure coding specialist with **no
general-reasoning score anywhere**, which is both why it is not placed higher
and why the placement rests on coding benchmarks alone.

**What the benchmarks say about tier 1, which is the bigger news:**
`GLM-5.3 Flash` is **#1 of 42 on Toolathlon** and 0.843 on Terminal-Bench. An
earlier draft of this file called its tier-1 position *"a budget decision, not
the measured-capability ordering"*. **That was too cautious — it is measured**,
and Toolathlon is agentic tool use, which is close to the most relevant
benchmark that exists for Step 2.

**Two cautions that are real and unresolved:**

- Independent coverage reports it is *"too closely tuned to Poolside's agent
  harness"* and *"can stray from the required format"*. Our citation contract
  `[B-17 "exact line"]` is **parsed**, so drift breaks the anti-hallucination
  mechanism, not merely the prose.
- The **free** variant caps output at **32,768** against `REPORT_MAX_TOKENS` of
  32,000 — **768 tokens of headroom**. The paid id `poolside/laguna-s-2.1` has
  131,072 and would spend credits, which is why the `:free` suffix is
  load-bearing and now pinned by a test.

**Measured live before it was configured, and it is better behaved than tier 1:**
**8 of 8** calls succeeded with and without `reasoning.effort`, `cost 0` every
time, and reasoning never ran away (0–421 tokens). So unlike `glm-5.3-flash`,
the reasoning field is **not** load-bearing here — it is set for consistency
with the chain rule, and because Laguna's `supported_parameters` really do list
`reasoning`. The API also accepts `max_tokens` of 40,000, above its own declared
cap, so our 32,768 is a deliberately conservative **local** guard.

**Source honesty:** only Terminal-Bench is confirmed by two sources (Poolside's
blog and llm-stats agree exactly at 0.702, so the vendor claim verified).
SWE-Bench Pro, SWE-Bench Multilingual and Toolathlon are **single-source**. And
cross-source noise is real — Poolside lists Claude Fable 5 at 88.0 where
llm-stats says 0.843 — so treat any gap under ~4 points as a tie.

#### Two tests this added, both mutation-verified

`test_every_cline_tier_is_a_model_the_api_actually_serves` pins the measured
allowlist. **Four of Cline's six free models answer 403 on every call**, and the
chain treats 403 as *next tier* — so a blocked model in `CHAIN` still produces a
report while silently burning a request per call. That is exactly how Gemma
stayed broken for weeks. The gate is per **model**, not per namespace:
`deepseek/deepseek-v4-flash` is an ordinary catalogue id and is refused, while
`z-ai/glm-5.3-flash` is on the same free list and answers — so the id cannot be
reasoned about, only measured.

`test_the_cline_tiers_do_not_share_a_quota_pool` defends a decision that would
otherwise live only in a comment. Whether Cline's quota is per account or per
model is **unknown**, so the split follows the asymmetry: sharing when it is
per-model silently loses a whole free tier; splitting when it is per-account
wastes exactly one request.

#### What was deliberately NOT built

- ~~**`poolside/laguna-s-2.1:free`**, the second reachable free model~~ —
  **BUILT the same day as tier 9**, once four benchmarks replaced "its quality
  is unmeasured". See
  [Laguna S 2.1 is tier 9](#laguna-s-21-is-tier-9-and-the-placement-is-measured--2026-09-13).
  The pool worry was answered rather than accepted: the two Cline tiers now own
  **separate** pools, because the cost of guessing wrong is asymmetric.
- **The other four free models.** `cline-free/muse-spark-1.3-contributor`,
  `cline-free/solar-pro4`, `cline-free/longcat-2.0` and
  `deepseek/deepseek-v4-flash` answer **403 on every API call**, so they cannot
  be tiers at all. Pinned by a test, because a 403 falls through to the next
  tier and would otherwise be invisible.
- **A smoke test of its own.** `tests/smoke/test_every_tier.py` parametrizes
  over `CHAIN`, so the new tier got weekly live coverage for free — the skip
  count went 46 → 47 and nothing had to be written.

### Reviving the dead tiers — investigated 2026-09-19

*GLM-5.2 on Mistral, and Cline's free roster. One is replaceable, three are
deliberately gated, and the gate is not what this file said it was.*

#### MISTRAL's GLM-5.2 IS PROPERLY DEAD — a third error shape, cleanest yet

```
2026-08-11   answered
2026-08-16   429, x-ratelimit-limit-tokens-minute: 0        "not entitled"
2026-09-19   DROPPED from GET /v1/models entirely, and a direct call says
             "This model is not available in your subscription tier"
```

**The wording is the whole diagnosis.** Mistral answers `Invalid model:
glm-5.3` for something that does not exist, and *"not available in your
subscription tier"* for `glm-5-2` and `zai-glm-5-2`. So the model still
**exists** there and is behind a paid plan. **Not revivable for free.**
Mistral's catalogue also shrank from 55 models to **46**.

**But the MODEL is revivable — just not at Mistral.** `z-ai/glm-5.2:free` on
OpenRouter answered 1 call in 4 on the first pass and first try on the
second, with the rest `429 upstream_provider_shared_pool`. **That is
congestion, not entitlement**, and the five-way rule already tells them
apart. The tier now points there, with a 32,768 context that keeps it off
reports and useful for Step 2's smaller jobs.

> **When a tier dies, ask whether the MODEL died or the ROUTE did.** Three
> weeks were spent treating GLM-5.2 as gone; it was Mistral that was gone.

#### CLINE's FREE ROSTER ROTATES, and the gate is the NAMESPACE

The list is different from the one recorded on 2026-09-13 — `longcat-2.0` is
gone and `deepseek/deepseek-v4-flash` became `cline-free/deepseek-v4.1-flash`.
Tested live, all five:

| model | result |
|---|---|
| **`z-ai/glm-5.3-flash`** | ✅ 200, 2.2s — our tier 1 |
| **`poolside/laguna-s-2.1:free`** | ✅ 200, 1.0s, cost 0 — our tier 12 |
| `cline-free/deepseek-v4.1-flash` | ❌ 403 |
| `cline-free/muse-spark-1.3-contributor` | ❌ 403 |
| `cline-free/solar-pro4` | ❌ 403 |

> *"X is only available via Cline product surfaces. If you are using an old
> version of Cline, please update to the latest version."*

**CORRECTION.** This file says *"the gate is per MODEL, not per namespace:
`deepseek/deepseek-v4-flash` is an ordinary catalogue id and is still
blocked."* With the current roster that is wrong — **every blocked model is
under `cline-free/`, and both working ones are under a vendor namespace.**
The old counter-example was an id that is no longer on the free list at all,
so it was refused for not being free rather than by a per-model gate.

#### THE THREE GATED MODELS WILL NOT BE REVIVED, and that is deliberate

The 403 is a **client gate**, not a quota or an account problem. Getting past
it means presenting our code as Cline's IDE, which is misrepresenting what the
software is in order to defeat an access control the provider put there on
purpose. **We do not do that**, and it is recorded here so nobody re-opens it
as a clever idea.

**What is legitimate is finding the same capability on another route**, and
for the most valuable one that already worked:

| Cline-gated model | elsewhere | free? |
|---|---|---|
| **DeepSeek V4 Flash** | **`deepseek/deepseek-v4-flash-0731:free`** on OpenRouter | ✅ **FREE — and it is now chain tier 4** |
| Muse Spark 1.3 Contributor | `meta/muse-spark-1.3-contributor` | ❌ $0.10/$0.20 per M |
| Solar Pro 4 | `upstage/solar-pro4` | ❌ $0.09/$0.36 per M |
| LongCat 2.0 (dropped from the roster) | `meituan/longcat-2.0` | ❌ $0.30/$1.20 per M |

**So the one that mattered is already recovered.** The other three exist only
as paid models anywhere we can reach.

#### The standing action, because the roster moves

Cline's free list changed twice in six days. `test_every_cline_tier_is_a_model_the_api_actually_serves`
pins what we use; the roster itself is worth re-reading before assuming a
`cline-free/` model is still gated — or that a working one still works.

```
https://api.cline.bot/api/v1/ai/cline/recommended-models     public, no key
```

### The gateway sweep — Zen, Kilo, Requesty, 2026-09-19

*Three platforms investigated from a proposal file, every claim tested live.
The chain went 26 -> 40 tiers. One platform is unusable, and the biggest win
turned out to be on a key we already held.*

#### ZEN IS UNUSABLE, and it says so in a typed error

Every one of its 8 free models, on the endpoints its own docs specify (Muse
via `/v1/responses`, MiMo via `/v1/chat/completions`):

```
error type:  "FreeTierError"
message:     "OpenCode's free tier can only be used from within OpenCode"
```

Identical with `Bearer`, with `x-api-key`, and **with no key at all** - so it
is not auth, not the endpoint and not the model id. The paid models answer
`401 "No payment method"`. It is the same client gate as Cline's
`cline-free/*`, and getting past it would mean presenting our code as the
OpenCode CLI. **We do not do that.** `ZEN_API_KEY` is not needed.

That cost the two biggest prizes in the proposal: **`jev-1.13-free`** (which
would have removed the only paid tier in the project) and **Muse Spark 1.3
Contributor** (AA 52, free nowhere else).

#### KILO RESELLS OPENROUTER — ON ITS OWN ACCOUNT, WHICH IS THE POINT

The error body settles what the catalogue could not:

```
Kilo        "user_id": "org_2uwFc1szZKyZweUX7p…"    Kilo's OpenRouter ORG
OpenRouter  "user_id": "user_3HREb0z4hSrOSnqLt…"    ours
```

Byte-identical otherwise. **An initial reading of "Kilo shares our quota" was
WRONG**, and the measurement that corrects it is the useful part:

```
our OpenRouter free-requests BEFORE:  17
3 successful Kilo calls
our OpenRouter free-requests AFTER :  17     delta 0
```

**Kilo spends Kilo's allowance.** So it is a genuine second pool:

```
OpenRouter    50 requests per DAY     our account
Kilo         200 requests per HOUR    per IP, their docs
```

One hour of Kilo is four times our whole OpenRouter day, **which is why a
Kilo route now goes BEFORE its OpenRouter twin** - the project's standing
rule that within one model the bigger free allowance wins.

**TWO CEILINGS, NEITHER OF THEM OURS.** The 200/hour is **per IP**, and we
work from a shared VPN exit, so it is split with everyone else on that
address - the thing that made OVH's anonymous tier unusable. And underneath
sits a per-model daily cap on OpenRouter's shared capacity: `inkling-small`
refused with `limit_source: openrouter_shared_capacity`,
`X-RateLimit-Limit 5000`, `Remaining 0`, resetting at midnight UTC, and
*"Credits don't affect this cap"*.

**Its key is OPTIONAL** - Kilo's docs say anonymous and authenticated free
requests are rate-limited identically, by IP. It sends **no rate-limit
headers** on a success and has no usage endpoint, so the remaining allowance
cannot be read. Blind, like Cline.

> **A gateway can be an independent business and still be a reseller.** What
> matters is not who owns it but WHOSE ACCOUNT the request is billed to - and
> the only way to find out was to read the `user_id` in an error body.

#### WHAT CONGESTION IS, AND WHY NO ACCOUNT FIXES IT

Back-to-back, same model, same minute:

```
qwen3.8-27b    OpenRouter 429 | Kilo(auth) 429 | Kilo(anon) 429    x2
glm-5.2        OpenRouter 429 | Kilo(auth) 429 | Kilo(anon) 429    x2
```

`limit_source: upstream_provider_shared_pool` - the **GPU host** (`Decart`,
`ModelRun`), one level below OpenRouter. Every account fails together.

> **Separate the ACCOUNT layer from the UPSTREAM layer.** A second account
> buys more requests; it buys nothing when the host behind it is full.

A 429 there is cheap - 0.7-1.2s, not retryable, straight to the next tier -
while a spent OpenRouter day lasts until tomorrow. That asymmetry is what
makes "try the congested-but-larger pool first" safe.

#### REQUESTY — a third route, independent of Google AND OpenRouter

200/day, no card, no trial expiry. **7 of 12 free models answered.** Its
value is independence rather than capability: a refused Google exit has
already cost this project every Google tier for a week, and Requesty serves
Gemma and Nemotron without touching Google or OpenRouter.

Dead, recorded so nobody re-adds them: `ling-3.0-tiny` 404, `laguna-m.1`
404, `laguna-xs.2` 404, `nemotron-3-nano-30b-a3b` **410 Gone**. No usage or
credits endpoint (both 404).

#### WHAT WAS ADDED, ALL SCORED ON AA v4.3

| tier | AA v4.3 | why |
|---|---|---|
| **Gemini 3.8 Flash ×2 keys** | **41** | position 2. **Free on a key we already had** - the biggest win of the sweep, and it needed no signup |
| Inkling Small (Kilo) | 26 | above Flash-Lite's 23. ⚠ Code Arena **#73** - weak coder |
| Step 3.7 Flash (Kilo) | 19 | between Flash-Lite and Gemma. Kilo's only exclusive free model |
| Muse Glimmer 30B (Requesty) | 18 | same band |
| 8 Kilo + 2 Requesty backup routes | — | second and third routes to models already in the chain |

**REJECTED, with the reason:** `ling-3.0-flash-fin` (AA 23, but **finance**-
specialised and our domain is code - the proposal file's own warning);
`nemotron-3-nano-omni` (AA 10, below Gemma); and `dots-3-note`, `nex-n2.5`
×2, `lfm-2.5-2.6b`, `leanstral-1-5`, which **have no AA or Arena page at
all** and therefore cannot be ranked. Unrankable is not unworthy - it is
unplaceable, and this project does not invent an order.

#### THE LIVE SWEEP — 29 of 40, and every failure had a sibling

```
503 overloaded   Gemini 3.8 (key 1), 3.7 x2       -> key 2 answered
500 server       Gemma 4 31B (key 1)              -> key 2 and Requesty answered
429 upstream     Qwen (Kilo), GLM-5.2 both routes -> Qwen: Cloudflare + Groq answered
429 daily cap    Inkling Small, Mistral x3
```

**Only GLM-5.2 lost every route**, and Mistral's three are one spent account.
The redundancy added today is what turned three of those into non-events.

#### A REAL DEFECT, AND A TRAP I WALKED INTO WITH MY EYES OPEN

**The defect.** `z-ai/glm-5.3-flash` was added as a Kilo tier by matching
Cline's tier-1 **model id** against Kilo's **catalogue**. Wrong list - the
catalogue is what a gateway SERVES, the free list is what it serves for
NOTHING. Kilo charges $0.150/$0.500 per M, so it answered *"Paid Model -
Credits Required"* on every call: a dead tier burning a request per report,
invisible because the chain swallows it.

`tests/smoke/test_gateway_tiers_are_free.py` closes it, and is a SMOKE test
deliberately - the lasting risk is not that mistake but **a gateway quietly
moving a model from free to paid**, and Cline's roster changed twice in six
days. A committed snapshot would be stale before it mattered.

**The trap.** After mutation-testing that guard I ran
`git checkout -- labpilot/llm/registry.py` to undo the deliberate break. HEAD
was an older commit, so the checkout **also reverted two uncommitted changes
in the same file** - the Requesty tiers and the paid-tier removal. The suite
stayed green, and a commit went out claiming work it did not contain. It was
caught only by a live sweep showing 36 tiers with the paid model at
position 2.

> This file already says: **"Never restore a mutation with git. Copy the file
> aside and restore from the copy."** Knowing the rule did not stop me
> breaking it - the same way the self-fulfilling-test rule was written down
> and violated within hours on 2026-08-17. **Take the copy; do not rely on
> remembering why.**

#### Three invariants this earned, all mutation-verified alone

```
a gateway route comes BEFORE its OpenRouter twin   200/hour beats 50/day
each gateway shares ONE quota pool                 their limits are not per model
every gateway tier is still FREE on its gateway    smoke, live catalogue
```

The second is the exact mirror of `test_every_google_tier_owns_a_pool_of_its_own`:
Google bills **per model** so those pools must differ, Kilo and Requesty bill
per account so theirs must not. **Same question, opposite answer, and getting
it backwards is silent in both directions.**

### Qwen3.8-27B and DeepSeek V4 Flash — added to the chain 2026-09-19

*Three tiers, placed on TWO independent sources. The blogs were wrong twice
and the index version was wrong once, so read the caveats before the numbers.*

#### THE MEASURING STICK CHANGED, and most of this file's AA column is stale

Artificial Analysis is now on **Intelligence Index v4.3**, and it is not the
scale the chain table was built on:

```
                      this file said     AA v4.3 today
gemini-3.5-flash-lite      37.4               23
gemma-4-31b                29.7               15
```

> **An index is a measuring stick, and measuring sticks get replaced.** Two
> scores from different versions look comparable and are not. The chain table
> now marks every re-read row with †; an unmarked row may not be compared
> with a marked one.

#### Two blog claims, both wrong, both nearly repeated here

| claim, from several blogs | truth, from the primary source |
|---|---|
| Qwen3.8-27B scores **52** on the AA Intelligence Index | **34** — AA's own page, v4.3, at `xhigh` |
| Qwen3.8-27B is **#9 at 1595** on Code Arena | **#18 at 1593** — the leaderboard itself |

A fourth source said the opposite again — that AA had **not indexed it at
all** and every number was Alibaba's. That was also wrong: the page exists.
**Three secondary sources, three different stories, and the primary settled
it in two fetches.** This project's sources rule keeps earning its place.

#### WHAT IS ACTUALLY MEASURED, and by whom

| | Qwen3.8-27B | source |
|---|---|---|
| AA Intelligence Index v4.3 | **34** — and **#1 of 142** open-weights models in the 4B-40B class | **AA's own independent eval** |
| LMArena **Code Arena** | **1593, rank #18** | **the leaderboard, independent** |
| output speed | **43.1 tok/s** — the slowest tier here | AA |
| SWE-bench Pro 61.7 · LiveCodeBench v6 90.3 · OSWorld 84.3 | — | ⚠ **Alibaba's own model card. NOT independently replicated.** Do not quote these as measured |

#### IS IT GOOD AT CODING? Yes — and the evidence is the GAP, not the score

The interesting part is not that it scores well. It is that its **coding rank
is far better than its general rank**:

```
                     AA v4.3      Code Arena       so...
Qwen3.8-27B            34         1593  (#18)
Gemini 3.6 Flash       34         1537  (#32)    TIED general, +56 Elo code
DeepSeek V4 Flash      35         1580  (#22)    AHEAD general, -13 Elo code
GLM-5.2                34         1592  (#19)    tied on both
```

**It ties Gemini 3.6 Flash on general intelligence and beats it by 56 Elo on
code.** That is a real specialisation, from an independent leaderboard rather
than the vendor — so **Step 2 should ROUTE code-writing sub-tasks to it**
instead of walking the chain, the same rule this file already applies to
Devstral and North Mini Code.

Proven live on a planted off-by-one, one short sentence each:

```
DeepSeek V4 Flash    7.9s   "window slice includes k+1 elements ... divides by k"
Qwen 27B (Groq)      1.5s   "xs[i-k:i+1] wraps around for early indices"
Qwen 27B (CF)       32.8s   "negative slice ... empty or incorrect early windows"
```

**Both Qwen hosts and DeepSeek found REAL bugs, and not the same one** — the
disjoint-blind-spot pattern this file already measured across generators.

#### THE WEAKNESSES, stated as plainly as the strengths

| | |
|---|---|
| **It is the SLOWEST tier in the chain** | 43.1 tok/s against Flash-Lite's 358.4 — **8x slower**. Measured end to end: **32.8s** on Cloudflare for one short answer at `xhigh`. Against a Step 2 problem that is already 98.2% generation, that is a real cost |
| **Cloudflare's budget is small** | 10,000 neurons/day, and **244 neurons** for one 4,860-token call — about **41 such calls a day** |
| **Groq can never serve a report** | 1,000 requests/day but **8,000 tokens per MINUTE**, covering prompt *and* reserved output. Modelled as `context_window=8_000` so `_check_fits` refuses it locally for nothing, exactly like GPT-OSS |
| **Its coding numbers are vendor-only** | SWE-bench Pro and LiveCodeBench are Alibaba's. Only AA and Code Arena are independent |
| **Thinking is ON by default** | `xhigh` is Cloudflare's default, and it is what makes the 32.8s. `low` and `medium` exist and are **unscored** |

#### THE SAME MODEL ON TWO HOSTS TAKES TWO DIFFERENT WORDS

```
Cloudflare  reasoning_effort=high   -> 400 "Supported types are xhigh
                                           (default), medium, and low"
Groq        reasoning_effort=xhigh  -> 400 "invalid Qwen3.8 reasoning_effort"
Groq        reasoning_effort=high   -> 200
```

Neither host accepts the other's value **for the same model**, so a shared
constant breaks one of them and `QWEN_CF_REASONING` exists. This file already
records that *the same model on two hosts has different LIMITS*; it also has
**different parameter vocabulary**.

`xhigh` is the setting AA scored at 34, so the chain placement describes the
configuration we actually send.

#### DeepSeek V4 Flash leads the pair, and speed is why

AA 35 against Qwen's 34 is **inside the ±1 interval — a tie** by this file's
own reading rule. Qwen wins Code Arena by 13 Elo, which is small. What is not
small:

```
DeepSeek   211.9 tok/s   1.05M context   TTFT 1.09s   free on OpenRouter
Qwen        43.1 tok/s    262K context                ~41 calls/day on CF
```

**Five times faster, four times the context.** A 13-Elo coding edge does not
buy a 5x slowdown when generation is already the blocking problem.

#### The 25 free OpenRouter models, tested 2026-09-19

**13 of 22 answered.** Worth knowing for Step 2 routing:

```
ANSWERED   deepseek-v4-flash-0731 (2.0s, 1.05M ctx) · nemotron-3-nano-omni ·
           north-mini-code · dots-3-note-preview (512K) · ling-3.0-flash x3 ·
           nex-n2.5-mini/pro · lfm-2.5-2.6b · openrouter/free ·
           nemotron-3-ultra (26.7s) · nemotron-3.5-lightning (177.9s !)

429        qwen3.8-27b · glm-5.2 · gemma-4-26b · gemma-4-31b · laguna-s ·
           laguna-xs   - ALL of them "upstream_provider_shared_pool"
403        inkling, inkling-small - "only available on agentic harnesses"
503        nemotron-3-super - NVIDIA overloaded
```

**The 429s are NOT our quota** — they are a shared free pool, and every one is
a popular model. `z-ai/glm-5.2:free` answered on 1 of 4 tries, which matters
because **this file records GLM-5.2 as dead**: that was *Mistral*, with
`limit: 0` meaning **not entitled**, and it never resets. Congestion is a
different failure and the five-way rule already separates them.

**`google/gemma-4-26b-a4b-it:free` and `gemma-4-31b-it:free` are a THIRD free
pool** for two tiers we currently run on two Google keys. Not wired in.

#### And the counter lied again

Right after 13 successful free calls the counter read `used: 2`; a minute
later, `used: 14`. **The same one-minute delay as the Jev billing counter** —
two independent confirmations that OpenRouter's counters are not live
instruments.

#### Cerebras is STILL dead, re-tested 2026-09-19 with a real key

```
GET  /v1/models   -> 200   qwen-3.8-27b, gpt-oss-120b
POST /v1/chat/... -> 402   "Payment required"  x-should-retry: false
```

Both models. The 2026-08-11 finding reproduced exactly, and with it the
lesson: **an issued API key is not a working API, and a catalogue answering
200 is not evidence.** ⚠ The variable in `.env` is spelled
**`CREBERAS_API_KEY`** — a typo, and this project already lost scheduled runs
to `OPENROUTE_API_KEY`.

#### Where else Qwen3.8 lives, and where it does not

`Qwen3.8-Flash-Next` (the 180B open checkpoint, ~125B main + 6B active) and
its hosted twin `Qwen3.8-Flash` have **no free no-card route**: ModelScope
serves it but needs Alibaba real-name verification, Featherless is a
subscription, and Alibaba/DeepInfra/Novita are paid. **Only the 27B is free**,
and only on Cloudflare, Groq and a congested OpenRouter `:free`.

Checked and carrying no Qwen3.8 at all: NVIDIA NIM, SambaNova, Hyperbolic,
Nebius, Fireworks, Mistral. **OVH AI Endpoints** has it free with no card and
even an anonymous tier, but the anonymous bucket is **2 RPM per IP** and
refused every call from our shared VPN exit — a free registered key would fix
that and is untried. **Synapse Garden** authenticates our key and then answers
**HTTP 500 `fetch failed`** on every endpoint, including `/models`; its
`/api/health` returns 200, which is the same trap as `GET /v1beta/models`.
