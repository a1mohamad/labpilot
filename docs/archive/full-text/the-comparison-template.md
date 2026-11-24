# Full text: The Comparison Template — designed 2026-08-14

[Docs home](../../README.md)

### The outline — send every chunk header, including the dropped ones

*(Raised by the user 2026-08-14: "how can we summarize A and B if we only select
some chunks?" The objection is correct and §1, §2 and §11 do not work without
this.)*

The model only receives the chunks the selector kept, so a description of B would
really be a description of half of B — **and the model would not know that**. On
the sample pair, A fits completely (18 chunks, ~4,300 tokens) but B does not
(~42 of 78 chunks).

**Fix: render the full ordered list of chunk headers first, marking which ones
carry their text.** The chunker already produced a header for all 78.

```
SIDE B — all parts, in order
  [text included]      [B_train.py · class QuoraTokenizer · def __init__ · lines 425-431]
  [text NOT included]  [B_train.py · class Trainer · def fit · part 3/5 · lines 1240-1270]
```

**Cost is only the dropped headers**, since the kept ones are already sent:
`36 × ~20 ≈ 800 tokens`, about 4% of `INPUT_BUDGET`.

It fixes four sections, not one. §1/§2 can say *"there is a class `Trainer` whose
body I did not read"*. §11 can name the exact missing line ranges. And §7 gets
its best possible wording for a miss: *"not found; lines 1100–1200 were not
included, and it may be there"* — which at Step 2 becomes the next search.

**This is the Step 0 form of `summarize`.** [Retrieval
Design](#three-query-sources--cheapest-first) already pins `summarize`'s query
source as *structural — README, file tree, file headers*, with no semantic search
at all. The outline is that idea, needed early. **Map-reduce summarization** (one
call per chunk, then one over the summaries) is rejected on cost: 79 calls for
one file against an OpenRouter cap of 50/day.

**⚠ OVERTURNED 2026-09-14 — see [the selector](../../step1/ask-path.md#13-the-selector-and-the-scenario-matrix-behind-it--decided-2026-09-14). The selector shares the leftover instead: A before B leaves A UNCAPPED, so a large reference starves B entirely, and it biases every code-vs-code comparison by upload order. When A fits, the two rules give the identical answer.**

**Filling A before B is the right selector rule — record it for Step 1, do not
build it now.** Dropping part of B is recoverable, because A still tells us what
to look for and we can report "not found". Dropping part of A loses a statement
we never learn exists, and it disappears silently. The current 50/50 split is
therefore wrong in principle — but `select()` stays broken on purpose, and it
does not bite on this pair because A already fits.


### Output length — `max_tokens` needs a real number

Rough count of the full template on the sample pair:

| Part | ~tokens |
|---|---|
| §7, about 18 rows | 1,100 |
| §10 explanation · §12 corrections | 1,000 |
| every other section | 2,400 |
| **answer total** | **~4,500** |

Thinking tokens sit on top of this and are not under our control, so **8,000 is
probably not enough** — see [Thinking
models](#thinking-models--the-count-is-at-least-four-of-seven). Start at 16,000,
and treat `finish_reason: length` as the signal, not the look of the text.


### What slice 4 built — `labpilot/prompts/`

| Module | Holds |
|---|---|
| `_ids.py` | `assign_ids` — one running counter per side |
| `context.py` | `build_context(chunks, selected)` — the outline plus the kept text |
| `instructions.py` | `Instructions`, `FULL` (14 sections), `CORE` (6 sections) |
| `builder.py` | `build_prompt`, `reserve` |
| `citations.py` | `Citation`, `find_citations`, `resolve` |

**Chunk ids are assigned at prompt time, not by the chunker.** `chunk_index`
restarts at 0 for every file, so a repo with four files would produce four
different `B-17`s. `assign_ids` walks the whole side with one counter, so
`train.py` ends at `B-40` and `model.py` starts at `B-41`. Nothing in `ingest/`
changed.


### Citations — deterministic quoting, not line numbers

The model **cannot count lines**, so asking for one is asking it to guess. The
mechanism that works is already named in the literature: **deterministic
quoting**. The model gives a pointer; the machine does the counting; the text
shown to the user is read back from our own file, never from the model.

```
model writes   [B-17 "count = count + 1"]
we check       does B-17 exist? is that line inside it?
we compute     newlines before it + chunk.start_line  ->  train.py:1203
we display     our copy of that line, never the model's
```

**Printing line numbers on every line was rejected on cost** — about 3 tokens per
line, roughly 3,000 tokens, which is 15% of the budget spent to buy something a
quote gives for free.

`resolve` matches **line by line**, not by searching the whole text: exact match
on the stripped line first, then "the line contains the quote". Indentation is
therefore ignored, which matters because the model will not copy leading spaces
reliably. When more than one line matches, `Citation.unique` is `False` — the
finding still stands, only the line number is a guess between two places.

**The citation format is fixed in the instructions** (`[B-17 "…"]`) purely so a
regular expression can find them afterwards. A citation nobody can parse cannot
be checked, and checking was the whole point.


### The outline does not scale past Step 0

Listing every chunk header costs ~2,400 tokens for the 96-chunk sample pair, and
about **40,000 tokens for a 2,000-chunk repository** — larger than the whole
budget. Step 1 must list **files**, not chunks. Recorded here so it is not
discovered during a demo.

**⚠ OVERTURNED 2026-09-14 — see [the selector](../../step1/ask-path.md#13-the-selector-and-the-scenario-matrix-behind-it--decided-2026-09-14). The selector shares the leftover instead: A before B leaves A UNCAPPED, so a large reference starves B entirely, and it biases every code-vs-code comparison by upload order. When A fits, the two rules give the identical answer.**

Related, and also for Step 1: **`select()` should fill A before B.** Dropping part
of B is recoverable, because A still says what to look for and the answer can be
"not found". Dropping part of A loses a statement we never learn exists, and it
disappears silently. The 50/50 split is wrong in principle. **Do not fix it now**
— it does not bite on this pair, because A fits completely.


### Thinking controls — three hosts, three different shapes

Verified from each provider's own docs on 2026-08-14. There is **no shared
field**; "they are all OpenAI-compatible" is true of the message shape and false
of this.

| Tier | Host | Where it goes | Values |
|---|---|---|---|
| 1, 2, 3 | Google | `generationConfig.thinkingConfig.thinkingLevel` | `LOW` `MEDIUM` `HIGH` |
| 4, 5, 7 | Mistral | **root** `reasoning_effort` — **and `top_p: 1` beside it** | `"high"` `"none"` |
| 6, 8 | OpenRouter | **root** `reasoning: {"effort": …}` | `xhigh`…`none` |
| 10 | Cloudflare | **not documented — unknown** | ? |
| 9 | Devstral 2 | **rejects it** — `400`, `code: 3051` | — |

`CLAUDE.md` previously guessed `thinkingConfig.thinkingBudget`. That is the
**Gemini 2.5** field; Gemini 3 uses `thinkingLevel`, and sending both is a 400.

**So the code carries two different things, on purpose.** `GeminiProvider` gets a
`thinking` field, because its setting is nested inside `generationConfig` and
cannot be merged at the top level. `OpenAICompatibleProvider` gets a generic
`extra_body: dict | None` that is merged into the payload, because inventing one
name for three shapes would be a lie. Both default to `None`, and both are data
in `registry.py` — variants that differ only in data are instances, not
subclasses.

**Two traps that make blind configuration dangerous:** Mistral answers **HTTP
422** when a model does not accept `reasoning_effort`, so setting it on `glm-5-2`
or `devstral-2512` could kill two tiers. And OpenRouter **silently drops** it for
some models — no error, no effect, which is worse than a failure. So every value
stays unset until one real request proves it, on the weekly smoke run that
already spends those requests.

**Free measurement, taken at the same time:** `_usage_summary` on the OpenAI shape
now also prints `completion_tokens_details.reasoning_tokens`, mirroring Gemini's
`thoughtsTokenCount`. That settles [which tiers are thinking
models](#thinking-models--the-count-is-at-least-four-of-seven) for nothing.


### `REPORT_MAX_TOKENS = 24_000`, and the tier it deliberately costs

*Corrected 2026-08-14. This section used to pin **16,000**, on the reasoning that
it is the largest value every tier accepts. Measurement overruled it.*

The tier limits are unchanged:

| Tier | output limit |
|---|---|
| Devstral 2 | **16,384** ← binding |
| North Mini Code | 64,000 |
| both Gemini | 65,536 |

But at 16,000 **both** runs were cut mid-report — `FULL` and `CORE` each returned
`finish_reason: MAX_TOKENS`. A truncated report is not a worse report, it is not
a report at all, so the constraint had to give somewhere. It gave at tier 5.

**So `REPORT_MAX_TOKENS` is 24,000 and Devstral 2 can no longer serve a full
report.** `_check_fits` raises before the HTTP call, which means the loss is
cheap — no request is spent, the chain records the tier and moves on. For
reports the chain is effectively six tiers, not seven.

**The invariant test was rewritten to say so out loud**:
`test_only_devstral_cannot_serve_a_full_report` asserts the unable-list is
*exactly* `["Devstral 2"]`. That is the important part — the test now fails if a
**second** tier ever drops below the report budget, which is the change that
would actually hurt. A deliberate loss is pinned; an accidental one breaks CI.

At 24,000 `CORE` finished (`STOP`). **`FULL` still did not** — see the run table
below. Raising the budget fixed `CORE` and did not fix `FULL`.


### `finish_reason` was promoted to `LLMResult`

*Changed 2026-08-14.* It had been logged only. [The `LLMResult`
rule](#llm-serving--fallback-chain) says a logged field is promoted "the moment
the UI or the budget validator needs the number", and the slice 4 measurement
needs it: `stop` means the report finished, `length` means `max_tokens` cut it
mid-sentence and the report is incomplete. Without the field, a truncated report
looks like a complete one in the saved artifact.

It passes the seam test — every provider reports it, and `_extract_message`
already returned it in both wire shapes. The field defaults to `"unknown"` so no
existing construction site had to change.


### What the smoke run writes

`pytest tests/smoke --run-smoke -q` spends **2 requests** and writes three files
into `artifacts/` (git-ignored):

```
2026-08-14_18-30_full_gemini-3.6-flash.md
2026-08-14_18-30_core_gemini-3.6-flash.md
2026-08-14_18-30_comparison.md
```

Each report carries `finish_reason`, chunks sent, prompt tokens, citations
written, **citations that resolve**, failed tiers, the answer, and the exact
prompt. The comparison file is one table so the two runs can be read side by
side.

**Read `model` and `tier` before believing the comparison.** If the two runs were
served by different tiers, the model changed and not just the prompt, and the
comparison is invalid — re-run rather than reasoning from it.

**Thinking-token counts stay in the log**, not on `LLMResult`, because Google and
the OpenAI shape name them differently. Read them with:

```bash
pytest tests/smoke --run-smoke -q --log-cli-level=INFO
```


### The measurement — five runs, all saved

*The plan was four runs, one variable each. Five were run. Results, not
predictions:*

| Run | prompt | max_tokens | chunks | finish | citations resolve | findings |
|---|---|---|---|---|---|---|
| baseline | bare | 2,000 | 60/96 | cut | ~50% | **10/18** |
| 1 | `FULL` | 16,000 | 63/96 | `MAX_TOKENS` | 1 of 3 | not scorable |
| 2 | `CORE` | 16,000 | 65/96 | `MAX_TOKENS` | 1 of 1 | not scorable |
| 3 | `FULL` | 24,000 | 63/96 | **`MAX_TOKENS`** | 22 of 45 (49%) | not scorable |
| 4 | `CORE` | 24,000 | 65/96 | `STOP` | 67 of 72 (93%) | **9/18** |
| 5 | `CORE` **stuffed** | 24,000 | **96/96** | `STOP` | **73 of 74 (99%)** | **11/18** |

**`FULL` was never scored, because it never finished.** It was cut at §7 at both
budgets. So the intended `FULL`-vs-`CORE` quality comparison did not happen —
`FULL` simply does not fit in one answer. Its 49% citation rate is an artifact of
truncation, not a measure of citation quality. **Do not read runs 1 and 3 as
evidence about template length.**

**Citations are solved.** 99% resolution on the stuffed run means deterministic
quoting works and the model can point at real lines. That failure from slice 3 is
closed and does not need more work.

**Coverage is not solved, and it is now the whole problem.** The bare prompt
found 10 with two-thirds of the context; the full template with *all* the context
found 11. Whatever the template is buying, it is not findings.


### `PROMPT_BUDGET = 26_000` — measured, not chosen

*Recorded 2026-08-14 after running the real numbers. The first plan said "keep
`INPUT_BUDGET` at 20,000". **Measurement proved that wrong**, and this is the
clearest example so far of why a number must be measured before it is trusted.*

At `20_000` the reserve of ~5,300 comes out of the chunks, so side B drops from
the baseline's 10,000 tokens to **7,332** — a 27% cut in evidence. Run 1 would
then change the prompt *and* delete a quarter of the code, and the result would
be unreadable.

**`INPUT_BUDGET = 20_000` always meant the *evidence* budget**, because there were
no instructions when it was set. Now there are, so the total must grow by the
reserve to keep the evidence the same. `PROMPT_BUDGET` lives in
`labpilot/prompts/builder.py`, beside `REPORT_MAX_TOKENS`, because both belong to
the task rather than to any model. The caller does
`select(chunks, budget=PROMPT_BUDGET - reserve(...))`, which adapts on its own
when the reserve changes.

Measured on the sample pair — 96 chunks, A=18, B=78:

| | instructions | reserve | chunks kept | evidence | whole prompt |
|---|---|---|---|---|---|
| baseline | 0 | 0 | 60 (B=42) | 14,273 | 14,273 |
| `FULL` | 2,272 | 5,336 | 63 (**B=45**) | **14,558** | 19,736 |
| `CORE` | 1,846 | 4,910 | 65 (**B=47**) | **14,791** | 19,545 |

Total request is ~19.7K in + 16K out ≈ 36K, far under tier 7's 128K floor.

**The prompt still lands ~6,000 under the budget**, and that is `select()`'s 50/50
split wasting side A's unused half — the flaw Step 1 removes. Do not fix it here.


### The measured ceiling of one call — 2026-08-14

*This is the most important result of slice 4, and it changes an assumption into
a measurement.*

Three runs on the sample pair, all `gemini-3.6-flash` at tier 1, `thinkingLevel:
HIGH`, `max_tokens = 24_000`:

| | chunks | findings (of 18) | invented | citations resolve | finished |
|---|---|---|---|---|---|
| baseline, bare prompt | 60/96 | 10 | 0 | ~50% | no |
| `CORE` | 65/96 | 9 | 0 | 93% | yes |
| `FULL` | 63/96 | — | 0 | 49% | **no — cut at §7** |
| **`CORE`, everything stuffed** | **96/96** | **11** | **0** | **99%** | yes |

**Stuffing the entire fixture — no retrieval at all — bought exactly two
findings**, and both needed parts the selector had dropped (`pos_class_weight`
defined and never called; the unfreeze off-by-one). The other **seven** misses
survived perfect context.

**So the split is measured: retrieval costs ~2, the single call costs ~7.**

**This section originally continued "and no prompt fixes the seven". That claim
was wrong, and the next section replaces it.** Scoring the answers row by row
showed the seven misses share one property that a prompt *can* address. The
literature below is still correct about the ceiling of a single call — it is just
not the binding constraint yet, because our prompt has not asked for the work at
all. Read this section as the long-run limit, and
[Why coverage is stuck](../../prompts/comparison-template.md#why-coverage-is-stuck--diagnosed-2026-08-14) as the
current one.

The literature on the long-run limit:

- **multi-needle decay** — recall falls as the number of facts asked for rises,
  and reasoning over them is worse than retrieving them
  ([LangChain](https://www.langchain.com/blog/multi-needle-in-a-haystack))
- **context rot** — accuracy declines as input grows *even when the evidence is
  present and well placed*
- **map-reduce wins** — smaller focused calls keep recall, because one large
  context full of irrelevant detail causes context confusion even in a
  200K-token model

The shape of our misses matches exactly: every Type-1 and Type-2 finding (A's
claims, a short list early in the prompt) was found, and four of the seven misses
are Type-3 — *things B does that A never mentions*, which requires walking a long
list late in the context.

~~**One call cannot reliably find many things in a long text. The fix is many
small calls, not better sentences.**~~

> **CORRECTED 2026-08-17, session 10.** Probe v2 asked **four** questions in
> **one** call, on 22,753 tokens, and recovered seven findings — five of which
> seventeen comparison runs never found. So the sentence above is not what our
> own data shows. The accurate version:
>
> **One call can only be asked one thing at a time. The fix is more questions,
> and small calls are how you ask them without the prompt collapsing.**
>
> The literature above is still right about the long-run limit. It was simply not
> the binding constraint — the binding constraint was that we asked one question.

**The agent is still a requirement, for two *measured* reasons** — neither of
which is the old "one call is too weak":

1. **Each question needs its own pass.** `verify`, `find_bugs` and `find_missing`
   are three different questions, and today proved each one returns what the
   others cannot see.
2. **Discovery needs a precision pass after it.** Asking for bugs manufactures
   some; `P1` was ranked first and was wrong. Nothing inside a single generative
   pass can check its own output.

*One line here was also wrong: "Step 0's ceiling is about 11 of 18, and chasing
it further would be tuning to one fixture."* 11 is where **this** prompt stops,
not where one call stops. The next section shows why, and predicts 16.


### Why coverage is stuck — diagnosed 2026-08-14

**The finding, in one line:**

> **Every one of the 11 findings carries an A citation. Every one of the misses
> has no anchor in A.**

Read the stuffed run's §3 table. `D1` through `D11` each cite a line of A, then a
line of B. The model walked **A's list of statements** and checked each one in B.
It produced roughly one row per claim A makes. It never walked B.

Now the misses, against the same test:

| Missed | Does A mention it? |
|---|---|
| #14 vocabulary capped at 20,000, so OOV is non-trivial | **no** |
| #15 rows dropped when empty *after* the regex | **no** |
| #16 three layer-norm modules built and never enabled | **no** |
| #17 `requires_grad` passed as an optimizer param-group key | **no** |
| #18 all-stopword question encodes to the zero vector | **no** |
| #9 threshold tuned on the split it is reported on | yes — but needs reasoning over B's own numbers |
| #10b the 12.1-point train/validation gap | yes — but needs reasoning over B's run summary |

The correlation is exact. **The model produced zero pure column findings.** Even
#11 (stopword masking) and #13 (cosine similarity), which `EXPECTED.md` files
under *unstated*, were found only because A happened to say something beside them
(`A-6 "excludes padding positions and nothing else"`, `A-9 "r = [u;v;|u-v|;u⊙v]"`).
Those were row findings wearing a column finding's clothes.

**Two things in the code explain it, and neither is "too many rules".**

1. **`CORE` deleted the column-walk instruction.** `FULL` §7 says *"first every
   statement A makes, **then every decision B makes that A never mentions**"*.
   `CORE` §3 says only *"Biggest effect first."* The second pass is gone — and
   `CORE` is what scored 11.
2. **`CORE` has no "problems in B alone" section at all.** `FULL` has §4 for
   exactly this. #16, #17 and #18 have nowhere to be written.

So the template that scored 11 had already removed the home of **five of the
seven misses**. The label vocabulary still offered `missing-in-A` and `defect`,
so the model *could* have used them — it simply was never told to walk B.

**The honest reading of the "too many rules" hypothesis.** It was a reasonable
guess from the numbers — 10 bare against 11 structured looks like the structure
paid for nothing. Half of it holds: two of our rules do cost us
([the four fixes](../../prompts/comparison-template.md#the-four-prompt-fixes--built-2026-08-14-not-yet-measured), items 3 and 4). But
the direction was backwards. **Cutting sections is what lost the findings.**
`CORE` is the short template, and short is where coverage fell.

#### What the literature calls this

- **Anchoring.** In LLM code review, *once the model latches onto one category of
  issue, it under-reports every other category*. The standard fix is to constrain
  each pass to one concern. Self-aggregation over 10 runs raised recall **118%**,
  which means a single pass finds under half of what is present
  ([Augment Code](https://www.augmentcode.com/guides/deep-code-review-recall-vs-precision)).
- **Single-pass extraction is known to be non-exhaustive.** Google's own
  extraction library ships multi-pass by default: 2 passes → 93% recall, 3 → 96%
  ([google/langextract](https://github.com/google/langextract)). The academic
  form is L3X — recall-oriented generation first, precision pruning second
  ([Recall Them All](https://arxiv.org/abs/2405.02732)).
- **Instruction density has a measured curve, and the failure mode is skipping.**
  IFScale: ~90% adherence at 10 instructions, ~70% at 50, ~40% at 150. Models do
  not degrade evenly — they **drop whole instructions**, and **middle-positioned
  ones go first** ([arXiv 2507.11538](https://arxiv.org/pdf/2507.11538)).
- **Serialising while thinking costs 10–30% of reasoning**, but *performance
  recovers whenever unconstrained reasoning precedes structured submission*
  ([Capacity, Not Format](https://arxiv.org/html/2606.09410)).
- **Decomposition beats one large prompt** — DecomP 50.6% against 36% for CoT on
  the same task ([Decomposed Prompting](https://www.emergentmind.com/topics/decomposed-prompting-decomp)).


### The four prompt fixes — BUILT 2026-08-14, not yet measured

*All four are in `instructions.py` now. One of them grew a second half while it
was being written — see [the A-walk correction](../../prompts/comparison-template.md#the-a-walk--the-correction-that-raised-the-prediction).*

**1. Make the enumeration positional, not semantic.** The prompt already sends
B's full ordered id list (`B-0`…`B-77`). Use it as a checklist instead of asking
for "the differences":

```
Walk side B's part list from the first id to the last.
For EVERY id write one line:
    B-12 | <a decision this part makes that A never mentions>
    B-13 | nothing
Do not skip an id. Do not merge ids.
Write this list before you write any table.
```

Free recall stops when the answer *feels* complete — that is why the model
stopped at 9, then 11. A positional walk makes stopping early **visible and
countable**: 78 ids in, 78 lines out. This is the single-call form of the Step 2
loop.

**2. Give the defect scan its own pass, placed before the comparison.** Anchoring
is category-level, so the standalone-bug job must not share a list with the
A-vs-B job. Put `PROBLEMS IN B ALONE` back into `CORE`, **before** the difference
table, so B is scanned with fresh attention rather than after the model has
settled into pair-matching.

**3. Let it think in prose before the table.** Findings as free bullets first,
then serialise into the row format. Right now the 10-column table *is* the
thinking, which is premature serialisation during enumeration.

**4. Delete `_CAUSES`.** ~25 lines of examples sitting mid-prompt that force no
behaviour — exactly the position IFScale says gets dropped. It costs budget and
buys nothing measurable. If removing it loses a finding, put it back; that is a
cheap test.


### The A-walk — the correction that raised the prediction

**Writing fix 1 exposed an error in the diagnosis, and it is worth keeping.**
The diagnosis filed #9 (threshold tuned on the split it is reported on) and #10b
(the 12.1-point train/validation gap) as *"needs reasoning over B's own numbers —
Step 2 work"*. That was wrong. Both are **stated in A**:

```
A_paper.md:212  "It is selected once, at the end of ... applied unchanged to the test set"
A_paper.md:232  "is 2.1 points. We take this as evidence that the dropout rates ..."
```

So they are row findings, not column findings. **The model walked A incompletely
— it answered some of A's claims and silently skipped others.** The 11 findings
were never "all of A"; they were "as much of A as the model felt like doing".

That is the same free-recall failure as the B side, so it needs the same fix.
**Both walks are positional now**, A as well as B. This costs almost nothing —
A is only 18 parts against B's 78.

**The general lesson:** *"the model found everything A stated"* was never
measured, only assumed, because the misses were sorted by type instead of
checked against A one id at a time. **A miss you have not looked up is not
evidence about the model — it is evidence about your scoring.**


### The revised prediction, so it can be falsified

$$
11
\;+\; \underbrace{2}_{\#9,\ \#10b\ \text{— the A-walk}}
\;+\; \underbrace{4}_{\#14,\ \#15,\ \#16,\ \#17\ \text{— the B-walk}}
\;+\; \underbrace{1}_{\#18\ \text{— the defect pass}}
\;=\; 18
$$

18 is the *arithmetic* ceiling, not a forecast. Every remaining miss now has a
section that asks for it, which is the most a prompt can do; whether the model
uses it is the open question. **Expect 15–16. Treat anything at or above 14 as
the fix working, and 11 as the diagnosis being wrong.**

**Measure it stuffed.** New `CORE` against the stuffed 11/18 baseline, both at
96/96 chunks, both tier 1. Stuffing removes retrieval as a variable, so the only
thing that changed is the prompt.

**Two things to check in the artifact before believing the score:**

1. **Count the walk lines.** B has 78 ids. If the walk has 40 lines, rule 6 was
   ignored and the fix did not actually run — that is a different failure from
   the fix not working.
2. **Read §6 for the banned comparison.** The two F1 numbers must not appear in
   one sentence. If they do, the material ban failed and the conclusion is still
   wrong even if coverage improved.


### What was actually built

| Fix | Where |
|---|---|
| walk A and walk B, positional | `CORE` §2 and §3; `FULL` §7 rewritten in place |
| defect scan before the comparison | `CORE` §4, ahead of §5 |
| prose before the table | the walks *are* the prose — no separate section needed |
| `_CAUSES` deleted | its useful hints moved inside walk B, where they are used |
| the comparison ban | rule 4 — a `NO` pair may not share a sentence anywhere below |
| walk completeness | rule 6, repeated in the closing for recency |

**A conflict had to be resolved, and it is the kind IFScale warns about.** Rule 1
demands a citation for every statement; rule 6 demands ~78 walk lines, most of
them saying "nothing". Left alone, the two rules fight. Rule 1 now carries an
explicit exception for walk lines that report nothing.

**`REPORT_MAX_TOKENS` rose 24,000 → 32,000.** The walks add roughly 96 lines to
every answer, and `CORE` only finished at 24,000 because its answer was short.
No further tier is lost — the next binding limit is North Mini Code at 64,000.

Measured cost on the sample pair: instructions 1,846 → 2,052 tokens, reserve
4,910 → 5,272, chunks selected 65 → 64. **One chunk, for four new sections** —
deleting `_CAUSES` paid for most of the walks.


### Two prompt rules the runs proved, both general

**1. A forced verdict must be first, and it must also bind the prose after it.**
*Corrected 2026-08-14 — the first version of this rule misread the artifact.* §2
demands `YES / NO / CANNOT TELL` and got it right in every run. §4 was recorded
here as having "allowed prose first", but the saved answer shows `NOT APPLICABLE`
**is** the first thing on its line, and the verdict itself is correct. The
failure is the paragraph *after* it, which performs the banned comparison anyway:
*"consistent with Side B's observed validation F1 of 0.8262 … lower than Side A's
test F1 of 0.851."*

So the fix that was proposed — move the verdict first — **is already satisfied
and would change nothing**. The real rule is stronger: **a correct verdict does
not constrain the prose that follows it.** Ban the material, not the conclusion —
after a `NO`, the two numbers may not appear in the same sentence anywhere below.

The general lesson is about method, not about §4: *the recorded diagnosis and the
saved artifact disagreed, and only re-reading the artifact caught it.* Artifacts
are kept for exactly this.

**2. Free recall stops when the answer feels complete.** §3 says "finish this
list completely" and the model stopped at 9, then 11. The one-call fix is to walk
the input by id — *"for every part of B, write a row or `nothing A does not
mention`"* — so stopping early becomes visible and countable.


### What Step 0 ships, and where each section goes later

| Section | Step 0 | Later |
|---|---|---|
| §0–§2 | yes | `summarize`, ×2 |
| §3 | verdict only, cannot halt the graph | the **correspondence gate**, a real halt (D78: it compares the two summaries, section 28) |
| §4 | yes, general knowledge only | `find_bugs`, walking files |
| §5–§6 | yes | the `result` claims and the answer instruction (**`extract_outcomes` was withdrawn on 2026-11-12, D108, section 31**) |
| §7 | one pass over the given context | `verify` + `find_missing`, one search per row |
| §8–§10 | yes | `diff_choices` + `explain_divergence`, routed to tier 1 |
| §11 | reported only | drives **re-retrieval** |
| §12 | yes | **`propose_fix`** — also not yet in the library |
| §13 | yes | `propose_next` |

**The template found two capabilities the library was missing** —
`extract_outcomes` (withdrawn 2026-11-12, section 31) and `propose_fix`. Add them to
[The capability library](../../agent/design.md#the-capability-library) when Step 2 is built.

**The honest Step 0 limit:** every `not in context` in §7 may be a false alarm
caused by the deliberately bad selector. Removing that is exactly what Steps 1
and 2 are for.

