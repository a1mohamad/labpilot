# Full text: Slice 7 — the decisions taken before any code, 2026-09-13

[Docs home](../../README.md)

## Slice 7 — the decisions taken before any code, 2026-09-13

*Taken in session 21, with the user, before a line of slice 7 was written.
Several of them overturn or narrow something this file already said, so they
are recorded here rather than rediscovered later.*


### 1. The API splits into INGEST and ASK

Today `POST /api/v1/compare` takes **both files on every request**, so every
question re-chunks and re-embeds the whole corpus. Slice 7 splits it:

```
once      POST /artifacts   [file]  ->  {"id": "a1"}     chunk, embed, store
per turn  POST /compare     {a, b, question}             search, rerank, answer
```

**The reason is not speed, although speed is the visible part.** This file's own
design says artifacts are **state**, not input — *"after an artifact is ingested
the only thing crossing the wire each turn is a prompt"* — and one endpoint
taking two files can never express that. Three things follow for free:

- **Retrieval becomes measurable.** Under one endpoint every request rebuilds
  the corpus, so the same corpus can never be asked two different questions.
- **0-, 1- and 2-artifact sessions cost one field**, not a rewrite of `api/`.
  The door takes **ids**, so a session simply *has* fewer of them — which is
  what makes [the artifact-count design](../../product/overview.md#artifact-count--flexible-input-focused-identity)
  nearly free at Step 2, exactly as this file predicted.
- **pgvector stops being scaffolding.** Under one endpoint we would embed,
  search, and throw the database away on every request.

**Measured, and it is why this is not a preference:** a FastAPI-sized repository
on `codestral-embed` was calculated at **166 minutes** per question under the
old shape. **MEASURED 2026-09-14 it is about 15** - the quota that figure
rested on is not enforced, see section 9. The argument survives the
correction: 15 minutes per question is still unusable, and paying it once is
still the point.


### 2. ONE LIST OF EMBEDDERS, SORTED TWO WAYS

*The user's rule, and it corrects a two-pool version I proposed first.*

There are **not** two pools of models. There is **one list — every embedder we
have — and the ORDER changes with the situation:**

```
fits the prompt budget   ->  STUFF IT. no embedder is chosen at all
small corpus             ->  sort by STRENGTH, walk down
large corpus             ->  sort by SPEED,    walk down
```

Walking down means: take the first model whose quota is alive. Google counts as
spent only when **both keys** are spent.

**Why one list and not two pools.** The two-pool version had a dead end: a fast
pool of two models, both exhausted, and nowhere left to go. A single list cannot
dead-end, because every model is always present — only its **place** moves. So
in the fast case, when `mistral-embed` and `embed-v4.0` are both gone, we
continue to *the next fastest still alive*, rather than failing.

**The threshold is TIME, not a chunk count:**

$$
T = \frac{t(A) + t(B)}{\text{rate of the model}}
\qquad
T > 6\ \text{min} \;\Rightarrow\; \text{sort by SPEED}
$$

Checked **before the first call**, which is the budget pre-check this file
already demands: *"chunk count is known before the first call, so check it
against remaining quota and refuse to start rather than dying halfway."*

**The speed order is arithmetic and is known today** — chunks embeddable in six
minutes, at the measured mean of 341.6 tokens per chunk:

| model | rate | chunks / 6 min |
|---|---|---|
| `mistral-embed` | 20M TPM, request-bound | **~10,800** |
| `embed-v4.0` (Cohere) | 10 req/min x 96 | **~5,760** |
| `codestral-embed` | 50K TPM | ~878 |
| `gemini-embedding-2` / `-001` | 30K TPM | ~527 |
| `bge-base-en-v1.5` (Cloudflare) | **UNKNOWN** — neuron cost for embedding is recorded nowhere | **must be measured** |

**Cohere really is fast**: 10 requests a minute times a 96-chunk batch is 960
chunks a minute, far quicker than codestral. Its 1,000-calls-a-month ceiling is
a budget factor for slice 8 to weigh **inside the order**, not a reason to drop
it from the list.

**THE STRENGTH ORDER IS SLICE 8's JOB, AND SO IS CLOUDFLARE'S SPEED.** BGE stays
in the list and slice 8 owes it **both** numbers — how fast it embeds, and how
well it ranks. Ordering by measured recall is this file's existing standard;
this rule just says the same list gets a second ordering.

**The fall-through is free, and it is important to say why it is not a
migration.** It happens *before* any vector exists, so nothing has to be
re-embedded. Switching models *mid-corpus* would be the unrecoverable case, and
this file already forbids it: *"never continue a half-finished corpus with a
different model."* The pre-check exists to stop exactly that.


### 2b. A SLOW INGEST IS OFFERED, NEVER IMPOSED

*The user's call.* In the fast case, if every genuinely fast model is spent, the
walk eventually reaches a slow one. ~~`codestral-embed` is **37 minutes** on a
5,386-chunk repository~~ - **that number came from a quota measured 2026-09-14
to be unenforced, and codestral really takes ~3.3 minutes (section 9).** The
rule below is unchanged and still needed; today the slow model it reaches is
`gemini-embedding-*` at ~63 minutes, which IS enforced.

**We use it anyway rather than refusing — but we ASK FIRST.**

```
pre-check   ->  "this will take about 63 minutes. continue?"
user says ok in the UI  ->  embed
user says no            ->  nothing is started
```

Working slowly beats not working, and *"come back tomorrow when the quota
resets"* is a worse answer than an honest estimate. But a 37-minute wait the
user did not agree to is not acceptable either, so the estimate is shown and the
choice is theirs.

**This whole path only exists when the corpus is too large to stuff.** If A and
B fit the prompt budget together, no embedder is chosen, nothing is stored, and
none of this runs. See the ladder below.


### 3. One embedder per SESSION — a simplification, NOT a safety rule

Both artifacts in a comparison use the same model. **Two models is a candidate
for a later version**, and the database already allows it: `v` is an
undimensioned `vector` and the model lives on the artifact row.

**This file's stated reason for the rule is WRONG, and is corrected here.**
[Open question 2](../../llm/embedder-chain.md#three-open-questions--answer-them-at-step-1-with-measurements)
says mixing would make *"the alignment matrix compare across models — the exact
`cos(E_A(q), E_B(d))` = noise failure"*. That is too strong, and it was repeated
for weeks without being checked:

```
search      question <-> A      vectors, in A's space
search      question <-> B      vectors, in B's space
COMPARISON  A <-> B             TEXT, read by the LLM
```

**A's vectors never meet B's vectors.** The similarity matrix compares *claims
extracted from A as TEXT* against B's chunks, so it can be embedded in B's space
and stays consistent. Mixing costs one extra query embed per turn, and nothing
else.

What genuinely survives is smaller than the claim it replaces:

| real cost of mixing | severity |
|---|---|
| two query embeds per turn instead of one | small, permanent |
| ~~the correspondence gate's threshold is calibrated **per model**~~ | **no longer true (D78, 2026-10-29): the gate reads the two summaries and has no cosine threshold** |
| a future caller could pool A's and B's **vector scores** in one sorted list | see below |

That last one is the only silent failure, and **it cannot happen today** —
`select()` loops `for side in ("A", "B")`, and `weighted_rrf` fuses by **rank**,
never by score. The warning describes a mistake nobody currently has a reason to
make. Note also that **reranked** scores come from ONE cross-encoder and so are
comparable across sides: merging A and B into a single 100-document rerank call,
which Cohere bills as one unit, is safe on *scale* and unsafe only on
*coverage* — which "fill A before B" already governs.


### 4. The full decision ladder, start to finish

```
1.  does EVERYTHING fit the prompt budget?
        yes -> STUFF IT ALL. no embedder, no search, no rerank, no database
        no  -> continue

2.  estimate the time. sort the ONE list by SPEED or by STRENGTH.
    walk down to the first live model.
    if the estimate is long, SHOW IT AND ASK before starting.
    embed + store

3.  search                  -> top 50    VECTOR_TOP_N   (slice 8 measures)

4.  gate: is the winner already obvious?
        yes -> skip the reranker

5.  rerank, if a tier is available -> top 10   RERANK_TOP_N  (slice 8 measures)
        no tier available -> skip(), keep the vector order, take the top N
```

**Step 1 is the one that keeps being under-weighted, and it is already this
file's rule** — *"add it up; if it fits, send it all"*. A paper plus a notebook
often fits, and then retrieval is not merely unnecessary but **harmful**, since
a bad retriever can hide the very line the report needs.

**Both N's are placeholders with no evidence behind them yet**, and slice 6 said
so explicitly: `recall@N` is monotone, so retrieval can find where MORE stops
helping and never where FEWER starts. What the frontier did settle for free is
that N in {20, 50} is eliminated, so generation only has to choose among
{3, 5, 10, 15}. And it is **two** numbers, not one, because the reranked and
vector-only paths have different recall curves.


### 5. MEAN TOKENS PER CHUNK IS 341.6, NOT 192 — measured 2026-09-13

[Slice 1](../../step1/embedders-measured.md#slice-1--the-measurement-and-the-model-is-settled-2026-08-20) records
**192 tokens per chunk** and concludes the routing rule's operational case
*"looks much weaker than it did"*. That number came from `B_train.py` — **one
file**. Chunked over this whole repository:

```
5,386 chunks   1,839,759 est tokens   mean 341.6   max 509
```

**1.8x higher**. ~~so `codestral-embed` on a real repository is **37
minutes**~~ - that followed from the published 50,000 quota, which section 9
measured to be unenforced; codestral really takes ~3.3 minutes. The
token-count correction stands on its own and the routing rule survives, but
NOT for this reason. **Condition 2 of the routing rule is
therefore STRONGER than this file claims, not weaker** — which is why rule 2
above exists at all.

> **A benchmark answers the question its fixture asks.** One file said 192; a
> repository says 341.6. Same code, same estimator, different population.


### 6. OPEN DEFECT: BGE's input guard is enforced with OUR tokenizer

`HTTPEmbedder._check_texts` enforces `max_input_tokens` using
`estimate_tokens` — our `chars/3`, calibrated on Mistral-shaped counts. **BGE
does not tokenize like that.** This file's own slice 1b measurement, the same
corpus embedded twice: **39,936 BGE tokens against codestral's 14,979**, which
is **2.36x** our estimate.

So BGE's real 512-token limit is about **217 of our tokens**, and on this
repository:

```
chunks                            5,391
refused by the guard (est > 512)      0   (0.0%)
TRUNCATED BY BGE (real > 512)     3,978   (73.8%)
```

**The guard passes every chunk and BGE silently truncates three quarters of
them** — the exact failure `max_input_tokens` was added to prevent, defeated
because the limit is enforced in the wrong units.

**Not fixed, and not urgent: BGE has no caller, so nothing is truncated today.**
**Strength of the claim:** the mechanism is certain; the 73.8% is extrapolated
from one ratio measured on one Python file. One Cloudflare call would settle it,
since the response reports real token usage. **Slice 8 owns it, and owes BGE
three numbers: its speed, its strength, and its real tokenizer ratio.**

> **A limit is only enforced if it is measured in the units the provider
> counts.** Ours is enforced in units we invented.


### 7. Cohere's exclusion is LIFTED, and its old reason was already stale

This file excluded `embed-v4.0` because *"Cohere is the reranker primary"* and
embedding there would starve reranking. **Slice 6 demoted Cohere to rerank tier
7 of 8**, behind four Google LLM tiers worth ~29,800 calls a day, so that
argument died without anyone noticing.

Under rule 2 Cohere is simply a member of the one list, and a fast one. What
remains true is a budget fact for slice 8 to weigh: 1,000 calls a **month** is
the smallest renewing bucket here, an embedded corpus spends it on **every
future query** permanently, and there is a second ceiling this file recorded and
never weighted — `x-trial-endpoint-call-limit: 10`.

> **When a decision has two reasons and one dies, say which one is still
> carrying it.** Otherwise the decision looks unsupported the day somebody
> checks the dead half.


### 8. TIME IS A PRODUCT CONSTRAINT, and it has TWO thresholds

*The user's decision, 2026-09-14, replacing a single 6-minute number that was
doing two unrelated jobs.*

```
6 min   ->  which ORDER to sort the embedder list by   (strength vs speed)
2 min   ->  whether to STOP and ask the user first     (a window, wait for yes)
```

They answer different questions, so they cannot be one number. A three-minute
ingest needs no reordering and **does** need a warning.

**Why the warning threshold is far lower than the routing one, and this is the
part that was missing:** embedding is ONE STAGE OF SEVERAL. Everything measured
in this project so far:

| stage | measured |
|---|---|
| vector search, exact | **34 ms** - negligible |
| rerank, `gemini-3.5-flash-lite` | **1.3 s** per call |
| rerank, `gemma-4-31b-it` | **18-22 s** per call |
| **one full report** | **52.7 s** live, `gemini-3.6-flash` |
| embedding | 0.9 - 61 min, entirely model-dependent |

**So a 2-minute embed is already a 3-4 minute answer, today, before the agent
exists.** `Ingested.minutes` is the EMBEDDING estimate only and must be
labelled that way; showing it as "total time" would be a lie the user acts on.


### 8b. THE AGENT MAKES IT SLOWER, NOT FASTER - and that is the trade

A reasonable assumption, and it is wrong: Step 2 is an **accuracy**
optimisation, never a speed one.

```
Step 0, ONE call        ->  13 of 19 findings
the 7 that were missed  ->  each needs a DIFFERENT question asked
```

This file already measured the cause: the misses came from asking ONE question,
not from a weak model or bad retrieval - *"one probe with a different question
recovered five findings that seventeen comparison runs had never found"*. Four
questions cost four calls. **Control flow is more steps, not fewer.**

> **"Simpler" applies to the DEVELOPER, never to the clock.** Each node does one
> thing, which is simpler to build and reason about. The user waits longer.

**But it is not 10x, because of routing.** A full report is ~10 calls and only
ONE needs the strong slow model - the gate, both summaries, claim extraction and
the batched `verify` calls all run on Flash-Lite or Gemma. Honest estimate:
**2-3x Step 0's wall clock, not 10x.** Three things already in the design fight
the rest: the correspondence gate halts a mismatched pair after one small call,
`verify` batches 5 claims per call, and a corpus that FITS the prompt budget is
stuffed with no embedding and no search at all.


### 8c. THE PRODUCT CONSTRAINT, written down so it binds

> **We will not ship a tool that costs ten minutes for a simple task.**

This is not a preference, it is a requirement on the planner. *"What does this
function do?"* must be one call, never the whole graph:

```
"summarize this"        ->  1 node
"find bugs"             ->  a few
"why do they diverge"   ->  the whole graph
```

The agent must not make EVERY question slower. It makes the hardest question
better, and the planner keeps the easy ones cheap. When a simple question does
get expensive, the fix is not a louder warning - it is to stuff instead of
embed, which step 1 of the ladder already does.


### 8d. THE END-TO-END NUMBER IS UNMEASURED, and slice 8 owes it

We have per-stage numbers and have **never measured a total**. The stage that
will dominate it - the agent - does not exist yet. So:

- `WARN_MINUTES = 2.0` **is a guess**, exactly like the 6, and is labelled as
  one in the code.
- **Slice 8 must measure the real end-to-end time**, on the same run that
  scores the embedder, and only that can set either number honestly.

Writing a total now would repeat the `r = 5` mistake: a number with no
derivation that gets quoted back six weeks later as if it were measured.


### 8e. WHERE THIS ACTUALLY LIVES: STEP 3, NOT HERE

*The user's framing, and it keeps slice 7 from growing.*

**The warning window, the "this is not ChatGPT" notice, the progress display -
all of it is STEP 3 work: the UI, Docker, the frontend.** Step 1 owes only the
NUMBER and the honest label; nothing in `api/` or `retrieval/` should try to
ask a user anything. `ingest_artifact` returns `minutes` and the caller decides.

It is recorded now rather than at Step 3 because the thresholds are being chosen
now, and a number chosen without its reason is the thing this file exists to
prevent.

**And one scheduled piece of work that follows from it:** the current page is
deliberately throwaway - *"throw away 100 lines, not an app"* - and it was built
when an artifact had no identity. **The frontend is worth REBUILDING at the END
of Step 1**, once the RAG system is complete and artifacts are real stored
things with ids, chunk counts and timings to show. Rebuilding it earlier means
rebuilding it twice.


### 9. THE PUBLISHED QUOTA DOES NOT PREDICT TIME — measured 2026-09-14

*The user refused an estimator built on `tokens_per_minute` and asked for one
built on our own measurements. He was right, and measuring it overturned four
claims this file makes above.*

**The finding, in one line:**

```
codestral-embed   DOCUMENTED quota   50,000 tokens/minute
                  MEASURED           590,000 tokens/minute
                  11.8x over, for 71 seconds, 37 requests, ZERO refusals
```

**And it is not universal, which is the whole difficulty.** Google enforces its
published number exactly — `gemini-embedding-001` and `-2` both 429 on the
SECOND call in a minute, measured at ~29,000 against a documented 30,000. So
the quota is right for one provider and 10x wrong for another, and a number
that behaves like that cannot predict anything.

#### Every embedding timing this project has

*Timeboxed pushes from a Frankfurt VPN exit, varying batch sizes on real
chunks from this repository. `sustained` means 4+ requests, long enough for a
limit to bite; `burst` means it never met one.*

| model | measurement | tok/min | requests |
|---|---|---|---|
| `codestral-embed` | burst, 1 batch | 619,000 | 1 |
| | sustained, 4 batches | 600,000 | 4 |
| | **sustained, 71s push** | **590,000** | **37** |
| | sustained, 30s push | 474,000 | 18 |
| | **MEAN of the multi-request runs** | **554,000** | |
| `mistral-embed` | burst, 1 batch | 703,000 | 1 |
| | sustained, 40s push | 520,000 | 25 |
| | **slice 4's 5-repo ingest** | **504,000** | **849** |
| | **MEAN of the sustained runs** | **512,000** | |
| `gemini-embedding-001` | burst, 1 batch | 274,000 | 1 |
| | **throttled, 6x 429** | **29,000** | 1 |
| `gemini-embedding-2` | **throttled, 6x 429** | **28,700** | 1 |
| `embed-v4.0` | **burst only** | 641,000 | 6 |
| `bge-base` | burst, day 1 | 288,000 | 1 |
| | burst, day 2 | 926,000 | 1 |
| | burst, 6 requests | 732,000 | 6 |

**The two Mistral-family numbers corroborate each other across sessions weeks
apart** — 520,000 measured today and 504,000 derived from slice 4's completely
separate 849-request, 45-minute five-repo ingest. That is the "do not rely on
one measurement" rule satisfied rather than asserted.

#### Three traps this exposed, and each one produced a wrong number first

**1. Averaging a burst with a throttled run is nonsense.** Google's two
measurements are 274,000 and 29,000; their mean is 151,717 and it describes
nothing. One sample never met the limit that governs the other. **So bursts
count only where no limit exists** (codestral, BGE) and are excluded where one
does (Google).

**2. A quota is not a throttle, and treating it as one was 12x PESSIMISTIC.**
`tokens / TPM` says a single 19,000-token call to codestral needs 23 seconds.
It takes 1.8. A provider lets you send a minute's allowance at once; the limit
only bites on the NEXT call.

**3. Timing ONE batch gives a burst rate that cannot be sustained.** The first
attempt at this measured one batch and got 619,000 for codestral — real, and
useless, because nothing had pushed against a limit yet.

#### What the estimator uses now

```
embedding_minutes = max( tokens / measured_tokens_per_minute ,
                         requests / requests_per_minute )
```

- **`measured_tokens_per_minute` is OURS**, on `Spec`, and is the only basis
  for the time. No provider reports throughput, so nothing can be learned from
  a header — the seed is all there is until we time ourselves.
- **`requests_per_minute` stays**, because it is a ceiling no throughput can
  beat: Cohere accepts 10 calls a minute, so a 57-request corpus takes 5.7
  minutes however fast the wire is. Measured at 641,000 tok/min, it would
  otherwise have been predicted at 2.9 minutes and been wrong.
- **`rate.tokens_per_minute` is recorded and NOT used to estimate.** It stays
  so `rates.learn()` can warn when a header stops matching it — which is how
  we would learn that Mistral has started enforcing.
- **A model nobody has timed returns `inf` and sorts last.** An unknown is not
  a promise, and the old fallback to the quota would have meant "when we do not
  know, use the number we measured to be unreliable".

#### The seeds are MEANS, and that was a correction too

The first version used the LOWER of each pair, on a "never under-promise"
instinct. **That instinct is a UX heuristic and it was applied in the wrong
layer.** The number does two jobs — it chooses the ordering AND it warns the
user — and a pessimistic value is helpful for the second and harmful for the
first: it abandons the strongest model earlier than the data justifies.

> **Keep the estimator unbiased. Padding belongs at the display.** Which is
> this file's existing rule in a new place: *a safety margin belongs on
> estimated quantities, never on known ones.*

#### What it predicts, and what it overturns

```
this repository, 1,839,759 tokens, 57 requests

  codestral      3.3 min     <- was claimed as 37 MINUTES above
  mistral        3.6 min
  cohere         5.7 min     <- requests bind, not throughput
  gemini        63.4 min     <- enforced, and genuinely slow
  bge           cannot - over its 684,000-token daily budget
```

**So the two-orderings rule of section 2 stands, and its motivating example
evaporated.** Codestral is both the strongest model and about as fast as
`mistral-embed`, so sorting by speed now only changes anything above roughly
**9,700 chunks**, or when Google is the best model still alive. The rule is
still right — it just fires far less often than the 37-minute figure implied.

#### Honest limits

- **One account, one VPN exit, two days.** Mistral may begin enforcing; if it
  does, codestral returns to 37 minutes and the ordering starts mattering
  again. The staleness warning in `rates.learn()` is what would tell us.
- **BGE's three samples span 3.2x** — 288,000 to 926,000 on the same work. It
  is the roughest number here, and academic anyway: its daily neuron budget
  stops it long before a rate does.
- **Cohere and BGE are BURST ONLY.** Both were capped at 6 requests to protect
  a 1,000-a-MONTH and a 10,000-neuron-a-DAY budget, so neither met a limit.

#### OPEN DEBT: nothing learns throughput at runtime

`rates.py` learns `requests_per_minute` from a header and warns on a stale
seed. It cannot learn throughput, because **no provider reports it** — only
timing our own calls can, and nothing does.

That is the piece that would make these seeds self-correcting, and it is
deliberately NOT half-built: accumulating across calls needs a decision about
what "elapsed" means — the sum of request durations (a burst rate) or wall
clock including our own gaps (the true ingest rate). Choosing wrong
reintroduces exactly the 619,000-against-554,000 error this section removed.

**It belongs with the progress display at Step 3**, beside slice 8's
end-to-end measurement.

> **A vendor's published limit is a promise about what they will REFUSE, never
> a prediction of what you will GET.** Measure the second; record the first
> only so you notice when it changes.


### 10. THE ASK PATH — decided 2026-09-14, before piece 4 was written

*Taken with the user in the same discipline as sections 1-9: the decisions
first, the code after. Three of them narrow or correct something this file
already said.*

#### 10a. THE STUFF CHECK MOVED, because artifacts became state

The ladder in section 4 was written for the single endpoint, where the file
arrived and everything was decided in one place. Option 2 split that in two,
so the check moved with it:

```
POST /artifacts   ALWAYS chunk, embed, store.        state. no decision.

POST /compare     do A and B TOGETHER fit the budget?
                    yes -> read every row back. STUFF.
                           no query embed, no search, no rerank.
                    no  -> search
```

**Ingest never skips embedding, and that is deliberate.** A small A may later
be paired with a huge B, and then A must be searchable. Deciding at ingest
would make an artifact usable in only one mode, which contradicts *"artifacts
are state"*. Embedding a small artifact costs seconds; the ask-time check costs
one SQL aggregate.

**The size needs no new column.** `estimate_tokens` is `ceil(chars/3)` and
`embed_text` is `header + "\n" + text`, so

```
select count(*), sum(length(header) + length(text) + 1) from chunks where ...
```

is exactly the number our Python would produce, in one round trip with no rows
moved. A stored token count would be a second copy of the truth — the argument
that already rejected `chunk_count`.

**And the cheap check must come FIRST.** Reading 24,000 rows back to discover
they do not fit spends ~14MB over the VPN to learn one boolean.

**`store/` therefore gains two functions** it has never needed: one that
measures an artifact without moving rows, and one that reads all of it back.
Search alone cannot serve the stuff path, because the stuff path has no query.

#### 10b. THE THREE NUMBERS — only their ORDER is a rule, the rest is a knob

*This file already said there are TWO numbers; it never said how they
constrain each other. The answer is: barely. One ordering is forced by
arithmetic, and every ratio inside it is an unmeasured default.*

**`SEARCH_LIMIT = 50` counts documents in ONE call, on ONE artifact.** That is
what `store.search()` takes - one `artifact_id`, one limit - and it is what
every measured number in this file already assumes: the dense top-50 was one
corpus, `we send 50 of a free 100` was one Cohere call, `61% of the 82-chunk
quora corpus` was one corpus, and Voyage refusing a 50-document window was one
call. **Read as a total, every one of those numbers halves.**

```
search     SEARCH_LIMIT = 50  PER SIDE      100 candidates
retrieve   VECTOR_TOP_N = 25  PER SIDE      <- THE CUT HAPPENS HERE
rerank     25 -> RERANK_TOP_N = 10          the reranker sees 25, not 50
```

**The cut comes BEFORE the reranker, and that is a decision.** The reranker
re-orders exactly what the vector path would have sent on its own. So it can
never introduce a chunk the vector path rejected - which means a BAD reranker
costs ordering and never content, and slice 6 measured that a bad one actively
hurts (`bge` took r@10 from 0.933 to 0.711).

**What it gives up is the rescue.** Ranks 26-50 are where a good reranker finds
what the bi-encoder ranked badly, and they are now discarded unseen. Measured:

```
requests   r@20 0.978   r@50 0.978    cutting at 25 costs 0.000
quora      r@20 0.941   r@50 1.000    costs one query of 17
```

**And it is what makes Voyage reachable** - see 10d.

**ONLY the ordering is a rule. Everything else is an unmeasured default.**

```
RERANK_TOP_N  <=  VECTOR_TOP_N  <=  SEARCH_LIMIT      all three PER SIDE
    10               25               50
```

The ordering is forced by arithmetic, not by taste: you cannot send more than
you kept, and you cannot keep more than you retrieved. A `RERANK_TOP_N` above
`VECTOR_TOP_N` would also make the DEGRADED path sharper than the good one,
which is backwards.

**`N/2` is NOT a rule, and calling it one was my error.** There is no reason
`VECTOR_TOP_N` should be half of `SEARCH_LIMIT` rather than 0.6 of it, or all
of it when the budget has room. It is a default, chosen for symmetry and
nothing else, and it is now written down as a knob so slice 8 sweeps it instead
of inheriting it:

```
SEARCH_LIMIT = 50  ->  retrieve 25?  30?  or all 50 if the budget takes it?
SEARCH_LIMIT = 30  ->  retrieve 15?  20?  25?  or all 30?
```

The two numbers are **joint, not independent** - a wider window with a hard cut
is a different system from a narrow window sent whole, and only the pair can be
scored. Slice 8 sweeps them together.

> **A ratio that looks tidy is still a guess.** `N/2` earned its place by being
> easy to say. pgvector's `ef_search = 40` and RRF's `k = 60` were both tidy
> defaults too, and both were measured to be wrong here.

**`RERANK_TOP_N` has a second, softer reason not to sit at the top of its
range.** Slice 6 measured that a good reranker shifts the recall curve LEFT -
reranked N=3 scores 0.882 where vector N=3 scores 0.765 - and that gain is only
collected by cutting harder. At `RERANK_TOP_N = VECTOR_TOP_N` the model gets
the same chunks in a better order and the compression is thrown away. **That is
an argument, not a measurement**, and it is the same sweep.

> **A constant's UNITS are part of its meaning, and a new section is the
> easiest place to change them by accident.** This was nearly written the other
> way - `SEARCH_LIMIT` as a total, 25 per side - and it would have silently
> re-scaled every rerank, neuron, token and corpus-ratio figure recorded above,
> none of which would have changed a line of code to disagree. The user caught
> it. **Before reusing a number in a new section, grep for it and read what the
> OLD sentences assume.**

#### 10b-bis. `SEARCH_LIMIT` HAS NEVER BEEN SWEPT — slice 8 owes it

Slice 6's measurement 2 varied how many chunks to **send** (3, 5, 10, 15, 20,
50). It never varied the **retrieval window** they were drawn from.
`SEARCH_LIMIT = 50` was written in slice 4 as *"retrieve wide, rerank to ~10"*
and has been a default ever since - the same class of unmeasured number as
pgvector's `ef_search = 40`, which quietly cost 14% of recall until someone
looked.

**Sweep it 10 -> 100, per side.** Both ends have a reason:

```
10    below this the reranker has almost nothing to reorder
100   Cohere bills per CALL up to 100 documents and we send 50,
      so half of every Cohere call is already wasted
```

Voyage caps the usable end far lower - 30 documents passed and 40 was refused
on a card-free account - so the sweep measures QUALITY and the chain decides
REACHABILITY, exactly as it does for the embedder.

#### 10c. PER SIDE, NOT MERGED — and slice 8 must measure it

This file said merging A and B into one rerank call is *"safe on scale and
unsafe only on coverage — which 'fill A before B' already governs."* Both
halves are still true. **The decision goes the other way anyway**, and the
reason is which failure you are willing to have:

```
merged     100 documents, ONE call      half the rerank budget
                                        one side can take every slot
per side    50 documents, TWO calls     coverage is STRUCTURAL
                                        twice the calls
```

Merged makes coverage depend on the selector behaving. Per side makes it
impossible to lose a side at all. **A guarantee in the shape beats a guarantee
in a downstream rule**, which is this file's own *"put a rule where it cannot
be broken, not where it can be checked."*

**And merged is the one shape that loses Voyage.** Per side hands it
`VECTOR_TOP_N = 25` documents (~9,040 tokens, under the 10K ceiling). Merged
hands it 25 + 25 = **50**, which slice 6 measured as refused at ~16,900 tokens.
So the cheaper option on rerank CALLS is the one that costs a whole rerank
TIER - which is exactly the kind of trade that cannot be settled by arithmetic
on one axis.

**SLICE 8 OWES THIS MEASUREMENT: merged against per side, on the same corpus.**
It is a real question and it is not settled by the argument above — merged
halves the rerank cost, and the rerank budget is the tightest one in the
project once `verify` needs a call per claim. Per side is the DEFAULT, not the
answer.

#### 10d. THE PRE-RERANK CUT MAKES VOYAGE REACHABLE — predicted, not measured

Slice 6 measured that Voyage cannot serve a 50-document window on a card-free
account at all: 50 documents (~16,900 tokens) refused, 40 (~13,100) refused,
30 (~8,900) passed, against a 10K TPM ceiling that counts a call whole.

Cutting to `VECTOR_TOP_N` before the reranker hands it **25**, and Voyage's own
published formula gives

```
t_q x N_d + sum(t_di)  =  20 x 25 + 25 x 341.6  =  ~9,040 tokens
```

Under the ceiling, and beside a measured 30-document call that passed at
~8,900. **So the pre-rerank cut is the first shape in which our second-best
measured reranker is usable free.** Reranking all 50 never could be.

**This is a PREDICTION and must be labelled as one.** It rests on our
`chars / 3` estimator, which slice 6 showed straddles Voyage's real boundary in
both directions - it called a 50-chunk quora window 11,400 tokens (passes) and
a 40-chunk requests window 13,100 (fails). One real call settles it, and it
costs 1 of ~16,000.

*A first draft of this section reached the same conclusion through a units
error - reading `SEARCH_LIMIT` as a total and deriving 25 per side. The
conclusion survived; the reasoning did not. Recorded because a right answer
from a wrong premise is the kind that gets quoted back and then collapses.*

#### 10e. "N in {20, 50} is ELIMINATED" was too strong — corrected

Slice 6 wrote that, and this file repeats it in three places. It overstates
what the frontier showed.

```
recall@N is MONOTONE  ->  N=50 has the HIGHEST recall of any N. always.
15 -> 50 buys          ->  0.000 recall
15 -> 50 costs         ->  DILUTION  <- a GENERATION property. NEVER measured.
```

The case against 50 rests entirely on dilution and lost-in-the-middle, which
are taken from theory and the literature and have not been measured once in
this project. So 50 is not eliminated — it is **unmeasured in the only
direction that could condemn it.**

`VECTOR_TOP_N = 50` therefore ships as the conservative choice: never discard a
chunk already paid for. **Slice 8 measures DOWNWARD from it**, and 20 or 15 is
where it is expected to land.

> **A metric that only moves one way cannot eliminate a value, only fail to
> reward it.** Slice 6 was right that retrieval cannot find the optimum, and
> then treated the flat region as if it had.

#### 10f. What piece 4 does NOT decide

| decided here | NOT decided |
|---|---|
| stuff at ask time, search when it does not fit | the stuff threshold — it is `PROMPT_BUDGET`, unchanged |
| per side reranking, `RERANK_TOP_N <= VECTOR_TOP_N` | merged vs per side — **slice 8** |
| **every top_n is PER SIDE**: `SEARCH_LIMIT` 50, `VECTOR_TOP_N` 25, `RERANK_TOP_N` 10 | all three values — **slice 8**, sweeping the window and measuring the cuts downward |
| exact search, no fusion on the query path | whether `wRRF` replaces it — **slice 8** |
| the reranker RUNS, chain assembled at entry | whether reranking SHIPS — **slice 8** |
| the search query is the user's question | claim extraction — **Step 2**, and this file already calls the question a bad query |



### 11. THE OUTPUT BUDGET — nine decisions, taken 2026-09-14

*Taken with the user during build step 1, which was interrupted by a question
this file could not answer: "why does raising `max_tokens` hurt a model that
would never reach it?" It could not answer it because the answer was a defect.
Four of the nine below are the user's, and two of them overturn something this
file already said. No code changed; every point is a decision or a debt.*

#### 11.1 `max_tokens` and `max_output_tokens` are a GRID, and the missing operator is `min()`

They are not two versions of one number. They are two axes:

```
max_tokens         what THIS JOB needs      changes per task, same on every model
max_output_tokens  what THIS MODEL can do   changes per model, same for every task
```

Both count the same bar - `T_out = T_think + T_answer`. What differs is who
owns them. `max_tokens` is SENT in the request; `max_output_tokens` never
leaves the machine, it is a note we typed into `registry.py`.

Neither can replace the other, because the number actually sent is a CELL:

| | gate (200) | summarize (1,000) | report (32,000) |
|---|---|---|---|
| Gemini (65,536) | 200 | 1,000 | 32,000 |
| Gemma (32,768) | 200 | 1,000 | 32,000 |
| Devstral (16,384) | 200 | 1,000 | **16,384** |
| Groq (8,000 total) | 200 | 1,000 | refused on INPUT |

$$
\text{sent} \;=\; \min\big(\text{what the job needs},\; \text{what the model can do}\big)
$$

**One number cannot index a grid.** A single global `max_tokens` would reserve
65,536 tokens on Gemini to write a one-word gate answer - and on Groq, where a
reservation is charged whether used or not, that is one call per minute instead
of many. A single per-model `max_tokens` would make Gemini write a 65,536-token
report and Gemma a 32,768-token one, so a difference between two reports could
no longer be attributed to the model rather than to the budget. That is the
same comparability rule that fixed `temperature: 0`.

#### 11.2 CLAMP, not refuse - but only when the number rises

`_check_fits` runs three checks, and only two earn their place:

```
1  max_tokens > max_output_tokens       -> refuse   <- WEAK
2  padded > max_input_tokens            -> refuse   <- real, Gemma's 16K/min
3  padded + max_tokens > context_window -> refuse   <- real, and what stops Groq
```

**Check 1 rests on an assumption that was later measured FALSE.** Its stated
reason is *"caught locally instead of costing a request"* - that is, the
provider would error. Mistral was asked for `max_tokens: 32000` on
`devstral-2512`, whose cap is 16,384, and answered **200**. It simply wrote
less.

So for ceiling-style providers, check 1 refuses a call that would have worked.
Today that is harmless: at `REPORT_MAX_TOKENS = 32_000` it excludes only
Devstral (genuinely too small, measured) and Groq (already caught by check 3).

**It becomes a real defect the moment the number rises past 32,768**, where it
would exclude Gemma and Laguna - tiers that serve complete reports right now.
A tier refused for being able to do exactly what we currently ask of it.

> **THE DECISION: keep the refusal today; if `REPORT_MAX_TOKENS` ever rises,
> change check 1 to `max_tokens = min(max_tokens, self.max_output_tokens)` in
> the same commit.**

The defect cannot land silently, and that is why waiting is safe:
`test_only_known_tiers_cannot_serve_a_full_report` asserts the unable-list is
EXACTLY `("GPT-OSS 120B (Groq)", "Devstral 2")`, so raising the number turns it
red and forces the conversation at exactly the right moment. That test is doing
more work than its name suggests - keep it when the task chains are written.

#### 11.3 The one real loss the refusal costs

When every tier that CAN finish is spent, the chain returns **503 and nothing**
- where a clamped tier could have returned a truncated report. And truncation
is already visible: `finish_reason` is on `LLMResult` and the page renders
`MAX_TOKENS` as a warning, so the objection *"it looks complete"* is answered.

Rare with 23 tiers, and it needs a second pass through a loop that is currently
simple and well tested. **Recorded, not built.** Fix it only if it happens.

#### 11.4 Four of six providers have NEVER been tested above their cap

| provider | asked above its cap | |
|---|---|---|
| Mistral | **200** - caps itself, writes less | measured |
| Groq | **413** - refuses, writes nothing | measured |
| Google · OpenRouter · Cloudflare · Cline | **unknown** | never tried |

Two measurements, opposite behaviour, and four blanks. Clamping sidesteps the
blanks entirely, because a clamped number is one no provider can object to.
**Do not generalise from either measured provider to the other four.**

#### 11.5 A `HIGH` report cannot fit a 32,768 cap - arithmetic, not policy

$$
T_{\text{think}} + T_{\text{answer}} \;\le\; C_{\text{out}}
$$

Measured on `gemini-3.6-flash`: a complete report needs `T_answer` about 5,655,
and `HIGH` spent `T_think` about 29,747.

$$
29{,}747 + 5{,}655 = 35{,}402 \;>\; 32{,}768
$$

So a 32,768-cap tier cannot serve a `HIGH` report at all. **Clamping does not
rescue it** - clamping only turns a refusal into a truncation. The lever is the
thinking level, not the budget, and that is measured: at `MEDIUM` the same
model finished with 2.5x more report.

> **More budget buys more thinking, not more answer.** Raising `max_tokens` to
> survive reasoning burn treats the symptom. `thinking` is the cause.

Visible even on a trivial prompt - the 2026-09-14 health check, 10 input tokens:

```
gemini-3.6-flash   STOP, 4 output tokens, 178 THOUGHT tokens
gemini-3.5-flash   STOP, 4 output tokens, 178 THOUGHT tokens
```

44x the visible answer, on "say ok", because every Gemini tier ships `MEDIUM`.

#### 11.6 A THINKING PRESET MUST RESTRICT THE CHAIN, NOT ONLY THE NUMBERS

*The user's, and it extends a rule this file already had.* CLAUDE.md said the
preset must set the level AND `max_tokens` together. It did not say this:

> **Deep is not a dial that exists on every tier.**

Two separate reasons a tier cannot serve it, and neither is about our code:

- **no knob at all.** `REJECTS_THINKING = ("gemma-4-31b-it",)` - Gemma answers
  **HTTP 400** to a thinking field. It has one mode, so "Deep on Gemma" is not
  a setting we can offer.
- **no room.** 11.5 above: thinking plus a finished report over-runs a 32,768
  cap.

```
Fast / Balanced   every tier eligible
Deep              only tiers that (a) have a thinking knob and
                                  (b) have C_out >= thinking + a finished report
```

**And the user's better fix for the silent-downgrade risk: build the chain so
it cannot happen.** Every real *Gemini* model carries a thinking level; only
Gemma does not, and Gemma is not a Gemini. So a Gemini-only Deep chain has no
downgrade to warn about - which is this file's own rule, *put a rule where it
cannot be broken, not where it can be checked*, applied one level up.

#### 11.7 A SCARCE TIER BELONGS IN AN EXPENSIVE CHAIN AND NEVER IN A CHEAP ONE

*The user's.* A Step 2 report is ~10 calls, and the strong models are the
scarce ones - every Gemini Flash is **20 requests a day**.

```
correspondence gate (~200 tokens)
  -> Gemma       HTTP 500     <- measured, about 1 call in 3
  -> Groq        refused
  -> Flash-Lite  ok
  -> ...if the chain continued: Gemini 3.7 Flash
```

One 200-token gate call would burn **1/20th of the day's report budget**, and
nothing would report it - the report still works, it just runs out of days
early. **A quota leak is silent by construction, so it needs a test.**

The partition is comfortable at 23 tiers:

```
cheap work   Cline x2 (free) · Gemma x4 (57,600/day) · Flash-Lite x4 (2,000/day)
             Groq (1,000/day, small jobs only) · Mistral (rate-limited, not capped)
reserved     Gemini Flash x6 (120/day) · OpenRouter x3 (50/day SHARED)
             Cloudflare GPT-OSS (~11 reports/day)
```

**The rule is one-directional**: a scarce tier may sit in the report chain, but
a cheap chain must contain none. Each task chain must still end in something
that cannot run out.

#### 11.8 THE REPORT CHAIN IS BUILT FROM CAPABILITY, AND DEGRADATION MUST BE VISIBLE

*The user's, and it corrects a loose claim made during the same conversation.*
"`EXPLAIN_CHAIN = CHAIN`, everything, strong first" is wrong as a description.

For TOKENS the chain already self-filters and it is free - `_check_fits`
removes Groq and Devstral before any request. **For THINKING there is no filter
at all**: `_check_fits` knows nothing about reasoning, so a Deep request that
falls through to Gemma returns a report that is not deep, and nothing says so.
That is a silent downgrade, which this project bans everywhere else.

```
report chain = tiers that can ACTUALLY serve THIS report, strong first
  "can serve" = tokens    <- checked today, free
              + thinking  <- NOT checked. the gap
```

The answer is not exclusion. It is the pattern this project already uses twice
- `skip()` returns `model=SKIP` so a missing rerank is visible, and
`MAX_TOKENS` renders as a warning so a cut report does not look whole:

> **Degrade, but never silently.**

Note the trap in the other direction: LOWERING `REPORT_MAX_TOKENS` would
silently let weak tiers into the report chain. The same exact-list test in 11.2
catches that too.

#### 11.9 DO NOT RESERVE THE STRONGEST TIER FOR THE REPORT ON AN ASSUMPTION

*The user's, and it challenges this file's own line "reserve tier 1 for
`explain_divergence`, which is the actual product."*

**Model strength was MEASURED and eliminated as the cause of coverage**, in
this file, in session 10:

> *Position, context and model strength are all eliminated as causes.*

The same model, at LOWER thinking, in ONE call, recovered five findings that
seventeen comparison runs had never found - once the QUESTION changed. Every
fix that worked that day was a deletion.

Two more measurements point the same way. Blind spots are **per-model and
disjoint** - `3.5-flash` never finds #12/#14/#18/#10b, `3.6-flash` never finds
`SKIP_CONNECTION`/loss-config/CUDA `Event` - and both score 11-13. So a
different model gives DIFFERENT findings, not more, which argues for VARYING
the model rather than maximising it. And in slice 6 the cheapest tier won
outright: `gemini-3.5-flash-lite` at 0.799 beat `gemma-4-31b` (0.732), Voyage,
and Cohere's purpose-built cross-encoder.

**The one place strength is explicitly required, and it has evidence:**
cross-language alignment - *"route the alignment reasoning to the top of the
generator chain, never to a weak tier"* - because the same algorithm in two
languages looks different and the gate can falsely reject it.

**THE HONEST GAP: the lean `REPORT` template has NEVER been run on a cheap
tier.** Every report number in this file came from `gemini-3.6-flash` or
`3.5-flash`. So 11.9 is well supported by adjacent evidence and untested
directly.

**The measurement is nearly free and slice 8 owes it:**

```
run the saved lean REPORT prompt, STUFFED, and score against EXPECTED.md on
    gemini-3.5-flash-lite     500/day pool
    gemma-4-31b-it         14,400/day pool
```

Two requests, on pools that cannot run out. If either scores near 13/19, the
payoff is large: **reports stop being capped at ~20 a day.**

#### What section 11 does NOT change

No code. `REPORT_MAX_TOKENS` stays **32,000**, measured to work at `MEDIUM`.
Check 1 stays a refusal. Every task chain named here belongs to **Step 2**, and
the Fast/Balanced/Deep control belongs to **Step 3**. The only thing that moved
today is that nine decisions are written down instead of being re-derived.



### 12. THE OUTLINE — build step 2's design, decided 2026-09-14

*Decided with the user before writing it. Four of the calls are theirs, and one
of them turned a single rewrite into a three-level ladder.*

#### 12.1 What the outline is FOR, in one sentence

It is a checklist of every chunk, marked sent or not sent, placed before the
evidence. Its whole job:

> **It lets the model tell "it is not there" apart from "I was not shown it."**

Without it a gap in OUR retrieval is reported as a defect in the USER's code -
a confident, false finding, which is the worst failure this tool can produce.
The worked case is the one this project already measures: the paper states
gradient clipping, retrieval drops the chunk holding `CLIP_NORM = 1.5`, and a
model with no outline writes *"the code does not implement gradient clipping."*

#### 12.2 The problem - measured 2026-09-14 on `labpilot/` alone

```
chunks             410
files               94
outline PER CHUNK   10,592 tokens    41% of PROMPT_BUDGET, before any evidence
outline PER FILE     2,193 tokens     8%
```

$$
\text{cost} \;=\; n \times \bar{h}, \qquad \bar{h} \approx 20\text{-}26\ \text{tokens per row}
$$

The saving is exactly the chunks-per-file ratio - only **4.4** here, because
this package has many small files. CLAUDE.md's worst measured case is far
uglier: **8,334 parts cost 210,541 tokens** against a 26,000 budget, so the
table of contents alone was 8x the entire prompt.

#### 12.3 THE DESIGN IS A LADDER, NOT A REWRITE

*The user's call, and it is better than the single per-file shape first
proposed.* Three renderings, measured per unit on the corpus above:

| level | shape | cost |
|---|---|---|
| 1 | **per chunk** - one row per chunk, full header | **25.8 / chunk** |
| 2 | **per file + `defines:`** - the file's distinct top-level labels | **44.9 / file** |
| 3 | **per file plain** | **23.3 / file** |

```
level 2 renders as:

  train.py  B-40..B-70  31 parts, lines 1-1420  ·  none included
            defines: load, Tokenizer, Trainer, evaluate, main
```

**Take the richest level that fits the outline's share of the budget.** A
corpus of a few hundred chunks gets per-chunk honesty for about 2,000 tokens; a
repository degrades to level 2, then to level 3.

**`defines:` is worth less than it looks, and the number is recorded so nobody
re-derives it optimistically: 410 chunks compress to 270 distinct labels, a
ratio of only 1.5.** Mean 2.9 labels per file, max 16. So level 2 is 2.5x
cheaper than level 1, not 20x - real, and not the order-of-magnitude win the
idea suggests.

#### 12.4 The stuff path keeps a FILE LIST and nothing more

*The user's call.* When everything fits, nothing is dropped, so the "what you
did not get" job disappears entirely.

**And a per-chunk outline there would be pure duplication**, which is the
measured reason rather than a stylistic one: `_text()` already renders
`{id}  {chunk.header}` immediately above every included chunk, so the outline
would repeat a header the model reads two lines later.

The file list stays because it is cheap and it tells the model how the corpus
is organised - navigation, not accounting.

**Note the arithmetic that makes this exact.** With `REPORT` at ~2,000 tokens
and a measured mean of 341.6 tokens per chunk:

$$
341.6n + 25.8n + 2{,}000 \;\le\; 26{,}000 \;\Longrightarrow\; n \le 65
$$

So the stuff zone is about **65 chunks across both sides**, where a per-chunk
outline would cost only ~1,700 tokens. Cheap, and still duplication.

#### 12.5 THE FILE RANGE ASSUMES CONTIGUITY, AND A TEST MUST PIN IT

*The user's call: a test, not a workaround.* `B-40..B-70` is only true if every
chunk of one file sits together in id order. It does today, because
`chunk_source` walks files in sorted order and `assign_ids` numbers the tuple
as it arrives - but **nothing enforces it**, and if it ever breaks the range
silently names the wrong chunks, which is the citation failure this whole
section exists to prevent.

Same class as slice 2's sorting rule: *chunk ids are positional, so if folder
order shifts between machines, `B-42` names a different file.* Sorting was
correctness there and contiguity is correctness here.

#### 12.6 PER FILE IS NOT FREE EITHER - recorded, not capped

*The user's call: record it, raise a cap later if needed.* 2,193 tokens for 94
files is 8%; a 500-file repository would be ~11,000 tokens, or **42% of the
budget**, with no evidence sent yet.

Level 3 of the ladder is the answer, and beyond it a cap or a per-directory
grouping. **Neither is built**, because we have no 500-file fixture and
choosing the number now would be a guess dressed as a decision - the same
reason `MAX_ARCHIVE_BYTES` stayed an xfail rather than being "fixed".

#### 12.7 "NOT INCLUDED" IS THE WRONG WORD, AND IT IS `instructions.py`'s JOB

*Raised by the user: won't a user who uploaded the whole file be confused to
read that 31 parts were "not included"?* Yes - and the phrasing blames the
upload for our own retrieval limit.

```
WRONG   "31 parts of train.py were not included"
RIGHT   "I searched 21 of 82 parts of your code. Clipping was not in those 21;
         it may be in the 61 I did not retrieve."
```

Two things make this survivable today. It only appears when the corpus really
did not fit - a small upload is stuffed whole and the line never appears. And
the API already reports `chunks: {side: {total, sent}}`, which the page renders
as `21/82 chunks`, so the user has the context before reading a word.

**But the wording rule belongs in the REPORT template, and CLAUDE.md's
evidence-basis axis already demands it** - *"seen in one, not found in the
provided context"* must be written as *"not present in the retrieved context"*,
never *"absent from the code"*. Whether the lean 1,997-byte rewrite still
carries that rule is **UNVERIFIED**, and it is worth checking: losing it is a
live defect in the product's most dangerous direction.

**This is Step 2's job, not build step 2's.** `context.py` decides what the
model READS; `instructions.py` decides what it WRITES. Only the first changes
here.

#### What build step 2 changes, and what it does not

```
prompts/context.py   _outline()  ->  the ladder above
prompts/builder.py   reserve()   ->  follows automatically
```

`_text()`, `assign_ids` and every id are untouched, so citations are unaffected.
`retrieval/` is step 3.

One over-estimate is knowingly left in place: `reserve()` adds an id prefix for
EVERY chunk rather than for the selected ones, because selection happens after
reserve. With the outline fixed it becomes the largest remaining slack. Leave it
until step 4 shows whether it matters.



### 13. THE SELECTOR, AND THE SCENARIO MATRIX BEHIND IT — decided 2026-09-14

*Build step 2 shipped; step 3 was stopped before a line was written, because the
user asked why A should be filled before B and the answer in this file did not
survive the question. Most of what follows is theirs, and one item OVERTURNS a
rule CLAUDE.md has carried since 2026-08-14.*

#### 13.1 Build step 2 is DONE, and it exposed the next bottleneck

```
outline PER CHUNK   187,695 tokens    of a 26,000 budget
outline PER FILE         26 tokens    measured on the same 8,333-part upload
```

`_outline` is a LADDER and takes the richest level that fits `OUTLINE_BUDGET`:
per chunk, then per file plus `defines:`, then per file alone. A side where
everything was sent gets a plain file list - nothing was dropped, so the
accounting job is void.

**And fixing it made the next defect visible.** `reserve()` charged a `B-1234 `
id label for EVERY chunk in the corpus, though only the selected handful is
ever printed:

```
before   reserve 25,616 of 26,000  ->  room    384  ->    4 chunks of 8,333
after    reserve    759            ->  room 25,241  ->  266 chunks
```

It was always an over-estimate; the per-chunk outline merely hid it. Without
removing it the outline fix would have bought 0 chunks -> 4 instead of -> 266.
**The real ~3-token per-chunk cost belongs in the SELECTOR**, which charges per
chunk as it packs - step 3.

#### 13.2 "FILL A BEFORE B" IS REJECTED — and this file has said it since 2026-08-14

The old rule, and its argument:

> *Dropping part of B is recoverable, because A still tells us what to look for
> and we can report "not found". Dropping part of A loses a statement we never
> learn exists, and it disappears silently.*

The asymmetry is REAL - a dropped A chunk is an **unknown unknown**, a dropped
B chunk is a **known unknown**. It still does not earn A priority, for four
reasons, and the last one is fatal.

**1. It covers `verify` only.** Session 10 measured the opposite direction:
removing side A ENTIRELY and asking *"what could go wrong?"* recovered **five
findings that seventeen comparison runs had never found once**. Seven of the
nineteen live in B alone with no A anchor at all. The flagship report runs both
kinds of question, so privileging a side is wrong for half the job.

**2. Half the scenarios have no reference.** Code-vs-code is SYMMETRIC - this
file's own template says *"never say one side is wrong, say only that they
differ."* There A-before-B biases the report by **upload order**.

**3. The slots are the user's choice.** `POST /artifacts` takes `side` as a
form field; nothing infers it. Privileging slot A privileges an upload habit.

**4. THE KILLER, and it is the user's: "A before B" means A has NO CAP.** A
30,000-token reference takes the whole budget and B gets **zero**. A comparison
with one side is not a comparison.

**And the rule was never load-bearing anyway.** This file's own note ends:
*"it does not bite on this pair, because A already fits."* **When A fits,
A-before-B and a fair split give the IDENTICAL answer.** They differ only in
the case the note says does not arise - so the fair rule loses nothing and
cannot starve a side.

#### 13.3 THE RULE: equal share, and the leftover flows over

```
pass 1   each side takes up to its share       SIDE_SHARE = 0.5
pass 2   anything unspent flows to the other side
```

| case | fixed halves (today) | A before B | share leftover |
|---|---|---|---|
| A small, B large | **wastes A's half** | good | **good - identical** |
| A large, B small | wastes B's half | **starves B** | good |
| both large | fair | **starves B** | **fair** |
| one artifact | half wasted | - | **all of it** |
| code vs code | fair | **biased** | **fair** |

It fixes the measured waste - 14,273 tokens sent of a 20,000 budget on the
sample pair - without guessing which file the user cares about.

**`SIDE_SHARE` is a KNOB, not a law**, and slice 8 may sweep it exactly as it
will sweep the retrieval window: *for now it is half; slice 8 may decide that
of a 50-document limit, 30 go to each side.*

**If a capability ever wants a side weighted, STEP 2's PLANNER passes that in.**
It is the only layer that knows which capability is running, and therefore the
only one entitled to the opinion.

#### 13.4 THE SCENARIO MATRIX — arrival order is irrelevant, TYPE decides

*The user's framing: the user sends whatever they want, however they want, and
the system must be ready for every shape.*

**Artifacts are STATE, so when they arrive changes nothing.** A capability
becomes reachable the moment its precondition is met:

```
turn 1  upload A   ->  summarize(A), find_bugs(A)
turn 4  upload B   ->  + verify, align, explain_divergence
```

Both at once, one by one, or B first - identical outcome. That is exactly what
Option 2's split of ingest from ask bought.

**What decides the MODE is the artifact TYPE, and it is known before any model
call:**

```
A = document + B = code   ASYMMETRIC   extract claims from A, verify in B
A = code     + B = code   SYMMETRIC    no claims exist - generate topics,
                                       search BOTH, compare topic by topic
one artifact              summarize, find_bugs
none                      answer_question
```

**`sources/defaults.py` already splits `DOCUMENT_SUFFIXES` from
`CODE_SUFFIXES`**, so the planner can pick the mode from the filename for free.
This CORRECTS a claim made earlier in the same conversation: the model does
decide the mode in its report, but the planner can decide it far earlier and
far more cheaply.

#### 13.5 A IS READ WHOLE, B IS SEARCHED — the asymmetry is ACCESS, not budget

This is where the unknown-unknown argument finally earns its place:

```
call 1     extract_claims(A)    ALL of A. no retrieval, no B
per claim  search(B, claim)     B is SEARCHED, never read whole
           verify(claim, hits)
```

A is read completely because a missed claim is a question never asked. B is
searched because it is too big to read. **They never share a budget here.**

It works because A is small: `A_paper.md` is ~3,900 tokens, a typical paper
8,000-15,000, against a 26,000 budget.

**And B still gets a WHOLE read when both artifacts exist** - `find_bugs` is a
1-artifact capability, so the planner runs it on B alone in its own call
whether or not A is present. That is not a fallback: it is where session 10's
five extra findings came from.

#### 13.6 ONLY ONE PLACE SHARES A BUDGET

```
Step 2      A whole (own call) + B whole (own call) + B searched per claim
TODAY       A and B in ONE prompt  ->  they share
```

Step 2 does not make the split fairer - it makes the question stop existing.
But the one prompt that still shares is **the flagship report the user reads**,
and the stuff path, so the split rule has to be right today regardless.

#### 13.7 Three holes this opened, recorded rather than built

**1. A HUGE REFERENCE HAS NO DESIGN.** Claim extraction assumes A fits one
call. A reference *repository* would need its own map-reduce - one pass per
file, then a merge - and nothing in this file covers it. Step 2 hole, **now Step 2 slice 12 (was 9; D26-D28)**.

**2. LOW COVERAGE SHOULD ASK THE USER, NOT GUESS.** *The user's idea.* On a
huge repo `sent 266 of 8,333` is 3% coverage, and a confident report over 3% is
the wrong answer. The honest one:

> *"I could not find what you asked about in the 266 parts I retrieved of
> 8,333. Point me at a file or a folder and I will look there."*

Same pattern this file already uses for a missing artifact - *"I need a second
file to compare"* - applied to COVERAGE instead of PRESENCE. Needs the agent
(to know the search failed) and the UI (to ask): **Step 2 + Step 3**.

**3. MAP-REDUCE'S COST OBJECTION IS STALE.** This file rejected it once -
*"79 calls for one file against an OpenRouter cap of 50/day"* - and that was
written before the quotas were measured. Gemma x4 is **57,600 calls a day** and
Flash-Lite x4 is 2,000. A 94-file walk is 94 calls of 57,600.

**The blocker is no longer quota. It is LATENCY**, which section 11 already
names as the budget nobody writes down. Re-cost it rather than inheriting the
old verdict.

#### What step 3 builds, after all of this

```
retrieval/   Chunk in, Chunk out. equal share + leftover. charges the id label
api/         SearchHit / StoredChunk -> Chunk       <- step 4, with ask()
```

**`retrieval/` is CORE and `store/` is an ADAPTER, so the selector CANNOT see
`SearchHit` or `StoredChunk`** - test_architecture forbids it, and both store
types lack `side` and `artifact_id` anyway. The build order's phrase "hits ->
chunks" therefore splits across two steps, and writing the converter now would
be a function with no caller.



### 14. SLICE 7 BUILD STEPS 1-3 ARE SHIPPED — 2026-09-14

*Everything below was built, measured and mutation-tested in one session on
branch `feat/ask-path`. Three of the decisions are the user's, and two of them
overturn something this file had already written down.*

#### 14.1 What shipped

| step | landed | mutations |
|---|---|---|
| **1** | `store/reader.py` - `measure()` and `read_chunks()` | 4, three real and firing alone |
| **2** | `prompts/context.py` - the outline ladder, and `reserve()` fixed | 4, all real |
| **3** | `retrieval/selector.py` - equal share + leftover; `dumb.py` deleted | 3, all real |

```
787 passed, 48 skipped, 1 xfailed     ruff clean both ways
```

**Step 1 - the cheap check comes first.** `measure()` is one round trip and no
chunk row crosses the wire; `read_chunks()` reads everything back, in
`chunk_index` order, and is only correct to call once `measure()` says it fits.
No size is stored: `count(*)` and `sum(length(...))` give it on demand, and a
stored copy is a second copy of the truth.

**A correction to this file's own SQL sketch.** It wrote a flat `+ 1` for the
newline in `embed_text`. The newline exists ONLY when the header does, so the
flat version over-counts by one character per header-less chunk - right by luck
on every real corpus, wrong by rule, and silent. The `case` expression counts it
exactly.

**One mutation SURVIVED and is recorded rather than hidden:** swapping the LEFT
JOIN for an INNER changes nothing, because `write_artifact` refuses an artifact
with zero chunks, so "stored and empty" is unreachable. The join is kept because
it is free and honest, but no test pins it - the same treatment `search.py`
gives the `::vector` cast.

**Step 2 - the outline, measured on an 8,333-part upload:**

```
outline PER CHUNK   187,695 tokens    of a 26,000 budget
outline PER FILE         26 tokens
```

**And it exposed the next defect immediately.** `reserve()` charged a
`B-1234  ` id label for EVERY chunk in the corpus though only the selected
handful is printed:

```
before   reserve 25,616 of 26,000  ->  room    384  ->    4 chunks of 8,333
after    reserve    759            ->  room 25,241  ->  266 chunks
```

It was always an over-estimate; the per-chunk outline merely hid it. **Without
removing it the outline fix would have gone from 0 chunks to 4 instead of to
266.** The real ~3-token charge now lives in the selector, where the chunks are
actually chosen.

`instructions.py` taught the old shape in all five templates - *"Parts marked
'text NOT included'"* - a format the ladder can no longer guarantee. Reworded in
place in four locations, keeping each preamble's shape. FULL and CORE were
updated too: a frozen baseline whose prompt describes a format we never render
could not be re-run anyway.

**Step 3 - the selector, and it behaves like this:**

```
A small / B huge   A   4   B  48    19,912 of 20,000
A huge / B small   A  48   B   4    19,912            <- exact mirror
both huge          A  24   B  24    19,488
B only             A   0   B  49    19,894
```

`test_neither_side_is_privileged` is the mirror, and the mutation that
re-implements "fill A before B" fires **four** tests. That decision is now
defended by code rather than by a paragraph.

#### 14.2 `VECTOR_TOP_N` WAS DOING TWO JOBS — the user found the conflation

This file used one number for two unrelated questions:

```
how many the RERANKER SEES            a quality and cost knob
how many we SEND if reranking failed  a degraded-path knob
```

They are not the same question and must not be forced to agree. **Four numbers,
four jobs:**

```
SEARCH_LIMIT     50   what search returns, per side
RERANK_WINDOW    --   what the reranker sees          <- NEW, and see 14.3
RERANK_TOP_N     10   what survives reranking
VECTOR_TOP_N     25   what we send when NO reranker ran
```

#### 14.3 THE RERANK WINDOW IS PER TIER, NOT GLOBAL — the user's call

*This supersedes 10b's "the cut comes BEFORE the reranker".*

The recorded cut to 25 bought three things: a bad reranker could only re-order,
half the rerank tokens, and **Voyage reachability** - 50 documents is ~16,900
tokens against a card-free 10K TPM ceiling, measured as 50 refused, 40 refused,
30 passed.

**Two things cut the other way, and they are stronger:**

**1. The cut discards exactly the queries reranking is best at.** Slice 6
measured reranking WINNING on `constant` questions (+0.186 MRR) - which are
where the bi-encoder is worst (0.354). The worked example is `D2`, which sits in
the FORTIES on codestral. Cut at 25 and it is gone before any reranker sees it;
no rescue is possible.

**2. The tier the cut protects is no longer at the front of the chain.** Slice 6
measured the four LLM tiers beating Voyage. `gemini-3.5-flash-lite` is listwise:
50 documents is ~17,000 tokens against a 1M context and 250K/min. It does not
care.

**So the cut was paying a real cost to protect a tier we may not reach.**

**THE ANSWER IS PER TIER, and the shape already exists.** Every reranker carries
`max_documents`. Voyage's says 1,000 - which is the BILLED tier's document
limit, and the wrong number twice over, because the free constraint is TOKENS
and not documents. Set it to its measured 30, and let `chain.rerank()` - the one
layer that sees both the documents and the tier - hand each tier what it can
take:

```python
reranker.rank(query, documents[: reranker.max_documents], top_n=top_n)
```

flash-lite then sees all 50, Voyage sees 30 and ANSWERS instead of burning a
request on a refusal, and no global compromise is imposed on either.

> **A limit that belongs to one provider should be modelled on that provider,
> never averaged into the pipeline.** The same lesson as `quota_pool`, and as
> Groq's `context_window = 8_000`.

**Slice 8 still owns the sweep** - its measurement 7 is exactly "where the cut
goes" - and a per-tier default does not prevent an experiment from overriding
the window for everyone.

#### 14.4 Step 4 is the ask path, and its decisions are taken

```
ask(conn, a_id, b_id, *, question, client) -> Comparison

1  measure(A) + measure(B)                cheap, no rows move
       fits PROMPT_BUDGET?  yes -> read_chunks both. STUFF, no embed, no search
2  embed the question with EACH artifact's own model
   search per side, SEARCH_LIMIT = 50
3  gate: should_rerank(scores). SKIP_MARGIN is None, so always yes
4  rerank PER SIDE, never merged, each tier taking up to its own max_documents
5  SearchHit / StoredChunk -> Chunk      add side and artifact_id
6  select -> build_prompt -> generate    already built
```

**D1 - a chunk's `side` comes from the STORED artifact row, not the request
slot.** `_artifact_id` is `f"{side}-{hash}"`, so the side is already baked into
the id and the same file uploaded twice is two corpora. Consequence: two `A-...`
ids must be REFUSED, because the prompt would have no side B.

**D2 - `skip()` truncates to whatever `top_n` it is handed**, so the degraded
path must not be handed the reranked number. Call `rerank(top_n=None)` and cut
afterwards on what actually happened:

```python
kept = RERANK_TOP_N if ranking.model != SKIP else VECTOR_TOP_N
```

`Ranking` already carries `model=SKIP`, so the degradation is visible and we cut
on the visible fact rather than on a guess.

**D3 - two artifacts may hold two different embedders**, because
`ingest_artifact` picks per artifact. Embed the question once per DISTINCT
model, and refuse an artifact whose model is not in `MIGRATION` at all.

**D4 - `ask()` has no caller until step 6**, as `write_artifact` had none after
slice 4. Scaffolding with a scheduled consumer, not dead code.

**THE TRAP THAT LIVES IN STEP 4**, and it is why
`tests/integration/test_retrieval_to_rerank.py` numbers its chunk ids from 100:

```
search()  returns  SearchHit.chunk_index   an ID in the corpus
rerank()  returns  POSITIONS in the list it was handed
```

`hits[p]` is right. Treating `p` as an id cites the wrong file and line with
full confidence.

And `UnknownArtifact` and `ModelMismatch` become genuinely reachable the moment
`search()` has a caller, so they are mapped and come off `ALLOWED_TO_ESCAPE`
here - at step 4, not step 6 as the build order says.

#### 14.5 What none of this decided

Every number is still slice 8's: `SEARCH_LIMIT`, `RERANK_WINDOW`,
`VECTOR_TOP_N`, `RERANK_TOP_N`, `SIDE_SHARE`, `OUTLINE_BUDGET`, merged vs per
side, and whether reranking ships at all. What changed is that each of them is
now a NAMED CONSTANT with its job written beside it, so a sweep changes one
number instead of a design.



### 15. SLICE 7 IS COMPLETE — steps 4, 5 and 6, 2026-09-14

*The ask path, the assembled rerank chain, and the door that finally takes IDS.
Two of the defects below were found by the USER reading the code rather than by
any test, and one of them had been sitting in a test file for weeks.*

```
804 passed, 4 skipped, 1 xfailed     unit + api + integration, ruff clean
                                     smoke deliberately not run
```

#### 15.1 Step 4 — `ask()`, the ladder

```
ask(conn, a_id, b_id, *, question, client) -> Comparison

1  measure both                    one round trip each, no chunk row moves
     fits?  yes -> read_chunks both. STUFF: no embed, no search, no rerank
2  embed the question with EACH artifact's own model, task="query"
3  search per side, SEARCH_LIMIT = 50
4  gate: should_rerank(scores)
5  rerank PER SIDE, never merged; each tier gets its own max_documents
6  SearchHit / StoredChunk -> Chunk, adding side and artifact_id
7  select -> build_prompt -> generate
```

**Three new errors, and each status is an argument rather than a habit.**
`UnknownArtifactId` is **404** - `StorageUnavailable` is 503 because the
database being down is OUR failure, while an id we never stored is a fact about
the REQUEST. `ArtifactSidesClash` is **422** - the side is baked into the id by
`_artifact_id`, so two `A-` ids is not a comparison and the prompt would have no
side B to walk.

**`ArtifactChanged` is 409, and it exists because the user refused
"unreachable".** The draft left `ModelMismatch` in `ALLOWED_TO_ESCAPE`, reasoning
that we pass `model=` from the very row `search()` checks it against. The user
said that made no sense. They were right - `measure()` and `search()` are TWO
round trips, and `write_artifact` DELETES then re-inserts, so re-ingesting an
artifact with a different embedder moves the model under a request already in
flight. Nobody's bug, and retrying fixes it, so a 500 would blame us and a 404
would blame the user.

**`ALLOWED_TO_ESCAPE` is now clear of `store/`.** `RerankError` took its place -
the rerank chain swallows it per tier and ends in `skip()`, exactly the
`LLMError` case.

**THE SEARCH PATH WOULD HAVE LIED, and this was caught while designing rather
than after.** `build_context` sees only the RETRIEVED chunks, and every one of
them is "kept" - so it rendered *"FILES - every part below is included"* over 20
rows of an 8,333-part corpus. That is precisely the failure the outline exists
to prevent. `build_context` now takes `totals`, which `measure()` already
supplies for free, and a partial side says so in the prompt:

```
SIDE B — 20 of 8333 parts were retrieved for this question.
         The rest were NOT searched, and you have not read them.
```

**`_fits` is deliberately conservative.** It charges the outline its full
`OUTLINE_BUDGET` even though the ladder usually renders far less, because the
real cost cannot be known without the headers - and the headers are the thing
the check exists to avoid fetching. So a corpus near the line is SEARCHED when
it could have been stuffed. That is the safe direction: a wrong `yes` means
reading ~14MB over the wire to discover it did not fit.

**`_best` takes its reranker INJECTED** (`rank=`, defaulting to the assembled
chain), which is what lets the door be tested with no provider at all - the same
shape `LLMReranker` and `LLMClientDep` already use.

#### 15.2 Step 5 — the chain assembled where both adapters are visible

`api/reranking.py`: `RANKING_CONFIG`, `PROVIDERS`, `_listwise`, `CHAIN`, `rank`.

**IT WAS BUILT AND NOT CONNECTED.** `_best` still defaulted to the bare
`rerank`, so the ask path would have used ONLY the cross-encoders and never
reached the four tiers that beat them. A chain built and never bound still
returns rankings - from the weaker half of the measurement, with nothing to
report it. `test_the_ask_path_reaches_the_assembled_chain_and_not_the_bare_one`
now pins it.

**The configuration is worth more than the choice of model:**

```
gemini-3.5-flash-lite  TUNED    MRR 0.799
gemini-3.5-flash-lite  UNTUNED  MRR 0.706
```

0.093 apart - wider than the gap between flash-lite and Cohere's purpose-built
cross-encoder. Every Gemini tier SHIPS `thinking=MEDIUM` for generation, so
reusing a `CHAIN` entry unchanged throws most of the gain away and the ranking
still looks plausible.

**`_listwise` is a FACTORY, not a loop body**, and that is load-bearing.
Building the lambdas inline would close over the loop VARIABLE, so all four
tiers would call whichever provider the loop ended on while each still reported
its own name. The chain would look healthy, one model would answer everything,
and the measured order would be fiction.

**And the code already existed in `tests/smoke/test_rerankers.py`** - the same
shape as `GEMMA_4_26B`, working code trapped where production could not reach
it. The smoke test now imports the production objects, so the weekly liveness
check exercises what actually ships.

#### 15.3 Step 6 — `/compare` takes ids

```
once      POST /artifacts   [file]            ->  {"artifact_id": "A-9f2c..."}
per turn  POST /compare     {a, b, question}  ->  the report
```

JSON, not multipart, because there are no files left to upload. `question`
carries NO `min_length` on purpose: a blank one must return through our own
envelope as `invalid_question`, and a Pydantic constraint would make FastAPI
answer in ITS shape - two error formats from one endpoint.

`services.compare()` is DELETED; it had no caller once the route used `ask()`.

**413 STAYS, and removing it was my error.** It is reachable two ways:
`ArtifactsTooLargeToCompare` is a 413 raised inside `_prompt`, which `ask()`
calls, and `RequestBodyLimitMiddleware` wraps every route.

**A real bug a test caught.** The route passed `questions=` instead of
`question=` - every `/compare` call would have been a `TypeError` and a 500. It
was found by the test that asserts the VALUES reach `ask()`, not by the one that
asserts a 200 comes back.

#### 15.4 The test migration was smaller than 23 tests suggested

`test_compare.py` held 23 tests and **eleven were never about comparing**.
`read_artifact` is the guard, it is SHARED by both routes, and once `/artifacts`
existed, testing it through `/compare` was one test per COMBINATION rather than
one per failure.

```
MOVED to test_artifacts.py   binary · size limit x2 · empty · pdf ·
                             scanned pdf · non-ascii · broken notebook
DELETED as redundant         "a rejected upload never reaches the model" -
                             at this door the loader runs INSIDE
                             ingest_artifact, so stubbing it out removes the
                             very code that does the refusing
REWRITTEN for ids            11 tests, the new test_compare.py
REWIRED                      test_api_over_the_chain.py - the store stubbed at
                             its own door, while the prompt, the chain and the
                             provider HTTP all stay real
```

#### 15.5 What slice 7 did NOT do

**`web/app.js` still posts two files to `/compare` and now gets a 422.** The
page is broken until the frontend is rebuilt, which this file already schedules
for the END of Step 1 - it was written when an artifact had no identity, and
rebuilding it before artifacts became real stored things would mean rebuilding
it twice.

**Every number is still slice 8's**, and each is now a NAMED CONSTANT with its
job written beside it, so a sweep changes one number instead of a design:

```
SEARCH_LIMIT 50 · VECTOR_TOP_N 25 · RERANK_TOP_N 10 · SIDE_SHARE 0.5
OUTLINE_BUDGET 4,000 · per-tier max_documents · merged vs per side
whether reranking ships at all
```

**And two measurements this slice ADDED to slice 8's list:** whether the
per-tier rerank window beats a global cut, and whether `explain_divergence`
really needs the strongest tier - section 11.9 says session 10 already measured
model strength out as a cause, and the lean `REPORT` template has never once
been run on a cheap tier.



### 16. SLICE 7 IS CLOSED — the review pass, 2026-09-15

*The twenty-fifth session wrote almost no product code and found three real
defects. It began by restoring two test files a session rewind had reverted on
disk, then wrote the tests the repository door shipped without, then swept
every slice 7 invariant that had never been mutated. Suite **808 -> 843
passed, 4 skipped, 0 xfailed**, and ~175s where it was ~260s.*

#### 16.1 The rewind, and the rule it produced

The session opened with `test_compare.py` reverted to its `eef2254` version
and `test_reranking.py` deleted — **on disk only**. Every commit was intact
and pushed. Hashing the working-tree blob against every commit proved nothing
unique was in it, and `git checkout --` restored both.

> **After a rewind, check git before rewriting anything.** The restore did not
> roll the project back — it moved it FORWARD, because the on-disk copy was
> older than HEAD. The suite went 668+1 failing to 808 passing.

#### 16.2 DEFECT 1 — the suite was spending live rerank quota on every run

The worst finding, and it was **measured, not suspected**. Any test reaching
the search branch of the ask path went straight to real providers:

```
Gemini 3.5 Flash-Lite -> 3.1 Flash-Lite -> Gemma 26B -> Gemma 31B
  -> Cohere -> Voyage -> Cloudflare
```

CLAUDE.md has said since the slice 6 notes that **tests must never call
Cohere** — its 1,000 calls a *month* are one bucket shared with chat and
embed, and it is the rerank primary.

**It hid behind a Python detail worth keeping:**

```python
def _best(question, hits, *, rank: Callable[..., Ranking] = _rank):
```

A default argument is evaluated **once, at import time**, so the function
object is captured. `monkeypatch.setattr(services, "_rank", ...)` rebinds the
module name and never reaches it. **A path that looked stubbed was not.**

> **Spending quota makes a suite slower, never redder.** Nothing would ever
> have reported this. It was found by patching `requests.post` to raise and
> watching four provider URLs scroll past.

**The fix keeps `labpilot.api.reranking.CHAIN` EMPTY for every non-smoke
test**, via an autouse fixture in `tests/conftest.py`. An empty chain is not a
mock: `rerank()` walks it, finds nothing, and ends in `skip()`, which is the
degraded path we already ship. So the default under test is *"no reranker was
available"*, and a test that wants reranking must supply its own.

`test_no_default_test_can_reach_a_real_reranker` joins the two rules in
`test_suite_rules.py` that already protect a real cost. Removing the fixture
fires it **alone** across 750 tests.

#### 16.3 DEFECT 2 — the API lied about how much it had read

Found by the new system test, the first thing to run both doors against each
other. On the search path:

```
corpus       120 chunks stored
the PROMPT   "20 of 8333 parts were retrieved"   <- honest
the RESPONSE "25 of 25 chunks"                   <- not
```

`ask()` already computed the true per-side totals and handed them to
`build_context`. **`Comparison` never carried them**, so the router counted
the chunks it had in hand and called that the total.

That is the number the page renders to prove the file was really read — and on
the search path it instead claimed the file was read **whole**. The same
dishonesty the outline totals were added to prevent, left in place one layer
up. `Comparison.totals` now carries it and the router prefers it.

> **Fixing a lie in one layer does not fix it in the next.** The prompt and the
> response are two audiences for one fact, and only one of them had been told.

#### 16.4 DEFECT 3 — a dead line, reported and NOT fixed (REMOVED 2026-09-28)

In `ingest_source`:

```python
chunks = tuple(replace(chunk, artifact_id=artifact_id) for chunk in chunks)
```

Removing it changes nothing. `ChunkRecord` has no `artifact_id` field, `_row`
takes the id from the `ArtifactRecord`, and grepping `labpilot/` shows **no
production code reads `Chunk.artifact_id` at all** — every match is a SQL
column name.

**No test was written for it**, because it has no behaviour to pin. This is
the case the mutation rule already names: *a mutation that survives is not
always a bad test; sometimes it is a false claim in the code.*

#### 16.5 What the new tests cover, and what was DELETED

**35 tests added across four levels**, every invariant mutation-tested.

| level | added | the mutation that proves it |
|---|---|---|
| unit (`test_ingest.py`) | 6 | hashing the container instead of the file paths breaks the zip-vs-clone test alone |
| unit (`test_ask.py`) | 5 | `task="document"`, the wrong embedder, a retired model, an outage, and `top_n` handed down |
| api (`test_artifacts.py`) | 11 | the case fold, the exactly-one-of guard, and each of the four error mappings |
| integration | 13 | per-file numbering fails four tests with `UniqueViolation: chunks_pkey` |

**Two tests were written and then DELETED for never firing alone** —
re-uploading the same file, and a 404 for a missing id. Both duplicate tests
that already exist: one test per COMBINATION rather than one per failure.

**The highest-value single test** is
`test_two_uploads_then_a_question_produces_a_cited_answer`: the model gives a
pointer and we read the line back from our own copy **after it has been
through Postgres**. A dropped header or a shifted `start_line` resolves to the
wrong line with nothing raising.

Its first fixture could not have caught that. A one-chunk file starts at line
1, so forcing `start_line=1` broke nothing — proven by the mutation. The
fixture was widened to two functions, so the cited line sits at **line 56**,
and the mutation then fires alone.

> **A fixture that cannot fail is worse than no test.** Two shapes cause it in
> this project: ids numbered from zero (an id is indistinguishable from a
> position) and a single chunk (a correct offset is indistinguishable from a
> lost one).

#### 16.6 The mutation sweep steps 4-6 never got

Sections 14-15 record mutations for build steps 1-3 and **none** for 4-6. Six
were run here. Four fired alone; **two survived**, which is what the exercise
is for.

| | mutation | result |
|---|---|---|
| P1 | the degraded cut uses `RERANK_TOP_N` | fires alone |
| **P2** | **`top_n` handed DOWN to the chain** | **SURVIVED — gap closed** |
| P3 | the LLM tiers keep their generation settings | fires alone |
| P4 | every tier gets the full window | fires alone |
| **P5** | **`min_length=1` on `question`** | **SURVIVED — gap closed** |
| P6 | two artifacts from the same slot are accepted | fires alone |

**P2**: `_best`'s docstring says the cut must happen AFTER the call, because
`skip()` truncates to whatever it is handed. Its test pins the CUT but injects
its own `rank`, so it never observes the ARGUMENT. A new test records the call.

**P5**: `CompareRequest` documents a deliberate decision — no `min_length`, or
FastAPI answers in ITS shape and a client parses two error formats from one
endpoint. The test sent `"  "`, and **two spaces clear a `min_length` of 1**.
The empty string is the case that pins it, now parametrized in.

> **A docstring recording a decision is not a guard.** Both of these had been
> written down, believed, and unenforced.

**Three mutations were BROKEN rather than surviving**, and each looked exactly
like a dead test: deleting an `except` clause left a `try` with no handler (a
SyntaxError), and two anchors matched zero or three times. `mutate.py` now
refuses to apply an anchor that is not unique, and prints *"the MUTATION is
broken, not the test"*.

#### 16.7 What was deliberately NOT added

- **No new smoke test.** The repository door calls no LLM, and its embedder is
  already covered by `test_embedders.py`. A smoke test would spend quota to
  prove wiring the integration tests prove for free, and *"do not add tests to
  raise a number"* binds hardest where the test costs quota.
- **No fix for the dead line** in 16.4 — reported instead, because deleting
  production code was not what the review was asked to do. **Removed
  2026-09-28.**
- **`MAX_ARCHIVE_BYTES` vs `MAX_UPLOAD_BYTES` is a NAMED OPEN QUESTION.**
  **CLOSED 2026-09-28: both are 10MB now - see section 12.6 of Step 2.** The
  archive limit is 10MB and the per-file upload limit is 5MB, so a zip between
  the two is refused by the upload guard and the archive limit never fires.
  That is the same shape as the xfail slice 7 just closed, one door further in.
