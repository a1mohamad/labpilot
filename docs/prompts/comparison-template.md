# The comparison template

[Docs home](../README.md)


**UPDATE 2026-11-24 (D142):** the templates FULL, CORE, REPORT, SCAN and COMPARE and `REPORT_MAX_TOKENS` are deleted. The answer uses `TWO_FILES` (`prompts/answer.py`), and its tokens are in `routes.TASKS`. The text below is the history. See [the cleanup](../step2/34-cleanup-before-slice-12.md).

## The Comparison Template — designed 2026-08-14

*Designed in session 6, before slice 4 was written. This is the output shape the
model must produce. Step 0 sends the whole thing in one prompt; Step 2 splits it
across capability nodes. The design is shared, so it is recorded once here.*

### The rule that produced it: never write the prompt from the answer key

`EXPECTED.md` may be used to **score** an answer. It may never be used to
**write** the prompt. Reading the fixture and then adding a prompt rule aimed at
one of its traps is training on the test set: the score rises and means nothing,
and the next repository is no better off.

**The leakage test, and it is mechanical.** Could this prompt run unchanged on a
physics paper vs a C++ solver, a statistics paper vs an R script, a systems paper
vs a Rust benchmark, or two notebooks? If a word only survives in one of those,
delete it. This bans every language name, framework name, file extension, metric
name, and field-specific term.

**This was learned by getting it wrong twice in one session.** First the design
was written around the fixture's threshold trap. Then it was rewritten around a
six-box ML decomposition — still parochial, because LabPilot is not MLPilot and
the code side is not always Python. The version below is the third attempt.

### Roles, not file types

Never say *paper* and *code*. Two neutral roles:

- **A — the reference.** Whatever states intent: a PDF, a spec, a README, a
  docstring, a paper, or an earlier implementation.
- **B — the subject.** Whatever is being examined.

| Mode | When | §7 becomes |
|---|---|---|
| **asymmetric** | A only *states*, B *does* | A's statements checked in B, then B's decisions absent from A |
| **symmetric** | both *do* — code vs code, repo vs repo | one **two-way** walk, topic by topic |

In symmetric mode there is no reference truth, so the only correct wording is
*"they differ"* — never *"B is wrong"*. Confidently naming a winner when neither
side is authoritative is a common failure and must be blocked by the prompt.

### Every finding is classified on four axes

One axis is not enough. A finding is only usable when its kind, its place, its
evidence and its size are all recorded.

**Axis 1 — kind of divergence:**

| Kind | Meaning |
|---|---|
| `contradiction` | A states X, B does not-X |
| `omission in B` | A states X, B does not do it at all |
| `omission in A` | B does Y, A never mentions it |
| `ambiguity in A` | A is under-specified, so B had to choose |
| `defect` | B is wrong by its own internal logic, independent of A |
| `scope` | B covers only part of A, or goes beyond A |
| `representation` | same behaviour, different expression |

`representation` is the one that must exist. Two languages, two libraries or two
formulations of the same operation look different and are **not** divergences.
Without a named category the model reports them as findings. With one, it must
classify them and then drop them. This is the cross-language false positive that
[Edge cases](../product/overview.md#edge-cases-to-handle-explicitly) warns about, solved by
classification rather than by an instruction to be careful.

**Axis 2 — box (where in the process it lives):**

$$
\text{outcome} \;=\; \underbrace{f(\text{input})}_{\text{procedure}} \;\rightarrow\; \underbrace{\text{measured}}_{\text{instrument}} \;\rightarrow\; \underbrace{\text{selected}}_{\text{reporting}}
$$

**Input · Procedure · Measurement · Environment · Reporting.** Five boxes, true
in any field. The earlier six-box list (data, model, objective, optimization,
evaluation, environment) is just the machine-learning dialect of these five.

**Axis 3 — evidence basis. This is the anti-hallucination axis:**

| Basis | Wording it forces |
|---|---|
| seen in **both** artifacts | "A states … · B does …" |
| seen in one, **not found in the provided context** | "not present in the retrieved context" — never "absent from the code" |
| **general knowledge** only | "this is unusual" — never "this is wrong" |

Without this axis, *"I did not see it"* gets written as *"it is not there"*. In
Step 0 that error is guaranteed, because the selector is deliberately bad.

**Axis 4 — impact:** `direction` (raises / lowers / unknown) · `magnitude`
(large / small / unknown) · `confidence` (high / medium / low). A difference is
not a cause until its direction is written down; that is the step that turns ten
differences into the three that matter.

### The catalogue of causes — domain- and language-neutral

**Input** — different source or version · different subset, filter or exclusion
rule · different ordering or grouping · different units, scaling or
normalization · different handling of missing or invalid entries · different
partition into parts used for different purposes · contamination between parts
that must stay separate · different size or sampling · encoding, format or
stored-precision differences.

**Procedure** — different algorithm for the same goal · a step present in one and
absent in the other · steps in a different order · different parameter values ·
different stopping condition · different approximation or shortcut · **a step
implemented but never invoked** · a value defined and then overridden elsewhere ·
different edge-case and boundary handling · different treatment of randomness.

**Measurement** — a different quantity is measured · **the same name means
different formulas** · measured at a different point in the process · measured
over a different scope · different aggregation · different protocol around the
measurement.

**Environment** — dependency version changing a default · numeric precision ·
hardware or parallelism changing operation order · uncontrolled non-determinism ·
platform, locale or path behaviour.

**Reporting** — **a knob was chosen using the same data the value is reported
on** · best-of-N instead of typical · one run with no variance · the value comes
from a different stage than claimed · a subset was shown · rounding or precision
· **the value is stale, produced by an earlier version of the procedure**.

Two entries deserve attention. *"Same name, different formula"* is probably the
most common silent divergence in any field. *"Stale number"* — the reported value
came from code that no longer exists — is the one nobody writes down.

### The template

```
§0  TASK
    One sentence: what was asked. Which sections will be produced, and why.

§1  SIDE A
    What it is (type, subject, purpose). What it claims to achieve.
    One paragraph. Citations.

§2  SIDE B
    What it is. What it actually does, in order. Its purpose.
    One paragraph. Citations.

§3  CORRESPONDENCE
    Do these describe the same work?   FULL / PARTIAL / NONE
    If PARTIAL: what overlaps, and what does not.
    If NONE: stop after this section.

§4  DEFECTS IN B ALONE
    Problems visible without the reference at all.
    Each: what, where, why it is wrong, evidence basis.
    "unusual" if the basis is general knowledge only.
    May be NONE.

§5  REPORTED OUTCOMES
    Table, one row per reported value, from either side.
    value | what produced it | how measured | how selected | citation
    May be NONE — many comparisons report nothing.

§6  ARE THEY COMPARABLE?
    YES / NO / CANNOT TELL, per pair, with the reason.
    If NO or CANNOT TELL: no difference may be computed anywhere below.

§7  DIVERGENCES
    The enumeration. Asymmetric: A's statements, then B's unstated decisions.
    Symmetric: one two-way walk, topic by topic.
    Each row: id | kind | box | basis | A cite | B cite | direction | magnitude | confidence
    Finish the list before writing anything below.

§8  RANKING
    The same rows, ordered by plausible effect on the outcome. Say why.

§9  DOES IT ADD UP?
    Expected effect of §8 versus the observed difference from §5.
    CLOSES / DOES NOT CLOSE / NOT APPLICABLE.
    If it does not close: give every honest reading. Never force agreement.

§10 EXPLANATION
    The causal story, built only from rows above, by id. No new claims here.

§11 WHAT COULD NOT BE DETERMINED
    What was missing, and what would settle it.

§12 CORRECTIONS
    Concrete changes to B. Each: the change, the location, the expected effect,
    the confidence.

§13 NEXT STEP
    One experiment. What it would settle, and what each result would mean.
```

**Two orderings are load-bearing, and both follow from
[a model cannot go back](#chain-of-thought--why-the-order-of-the-output-is-a-design-decision).**

- **§3 sits before §4 and §7.** If the two artifacts do not correspond, every
  finding below is invented. The halt has to be placed where it can still halt
  something.
- **§9 sits before §10.** The model must write *"does not close"* before it is
  allowed to tell a story. Then there is no story left to force. The general
  failure being blocked is *the model bends the evidence so its story closes* —
  not the fixture's specific threshold trap, which is only one instance of it.

### Four rules that hold the template together

1. **`NONE` is a correct answer, and the instructions must say so.** A section
   that demands a value will be filled with an invention.
2. **The model never chooses which sections to skip.** It will drop the one that
   threatens its conclusion. Section selection belongs to the planner at Step 2.
3. **Every claim carries a citation, or it is deleted.** A claim that cannot
   point at provided text was invented — the existing
   [citation rule](../agent/design.md#the-citation-rule--the-strongest-anti-hallucination-mechanism).
4. **Wording follows the evidence basis mechanically**, per axis 3 above.

### Chain of thought — why the order of the output is a design decision

A model writes one token at a time, and each token is chosen from the tokens
already written:

$$
P(y_t \mid y_1, \ldots, y_{t-1}, \text{prompt})
$$

There is no eraser. A wrong claim written early becomes the *context* for
everything after it, so the model then reasons correctly from a false premise —
and later text is bent to defend the early claim. Two consequences:

- **A check placed after the conclusion is not a check. It is a justification.**
  Any test that could invalidate the conclusion must be written **before** it.
- **A forced verdict cannot be skipped, but free prose can waffle around a
  question.** That is why §3, §6 and §9 demand one word from a fixed set.

A second, separate reason CoT works: a transformer does a fixed amount of work
per token, so the only way to spend more computation on a problem is to emit more
tokens. With `m` reasoning tokens before an `n`-token answer, the work goes from
`n·c` to `(m+n)·c`. **`m` is chosen by us, in the template.**

We use **structured** CoT — we write the steps — not free-form *"think step by
step"*. Free-form lets the model pick its own steps, and it will skip the step
that ruins its story. **Self-consistency is rejected**: sampling N chains costs
N× the quota, and the `temperature: 0` rule forbids sampling anyway.

**What CoT cannot do**, so it is not over-trusted: it cannot create knowledge
that is neither in the weights nor in the context (that is what retrieval is
for); a wrong first step makes the answer *more* confidently wrong; and the
written reasoning is not proof that it caused the answer (**unfaithful chain of
thought**). Citations, not CoT, are what make a claim checkable.

### The outline — send every chunk header, including the dropped ones

*(Raised by the user 2026-08-14: "how can we summarize A and B if we only select some chunks?" The objection is correct and §1, §2 and §11 do not work without this.)*

The model only receives the chunks the selector kept, so a description of B would be a description of half of B — **and the model would not know that** (on the sample pair A fits, 18
chunks ≈ 4,300 tokens, B does not, ~42 of 78). **Fix: render the full ordered list of chunk headers first, marking which carry their text** (the chunker already made a header for all
78): `SIDE B — all parts, in order` / `[text included] [B_train.py · class QuoraTokenizer · def __init__ · lines 425-431]` / `[text NOT included] [B_train.py · class Trainer · def fit ·
part 3/5 · lines 1240-1270]`. Cost is only the dropped headers (`36 × ~20 ≈ 800` tokens, ~4% of `INPUT_BUDGET`). It fixes four sections: §1/§2 can say "there is a class `Trainer`
whose body I did not read", §11 can name the exact missing line ranges, and §7 gets its best wording for a miss ("not found; lines 1100-1200 were not included, and it may be
there"), which at Step 2 becomes the next search. **This is the Step 0 form of `summarize`** ([Retrieval Design](../retrieval/design.md#three-query-sources--cheapest-first) pins `summarize`'s query source
as structural — README, file tree, file headers); **map-reduce summarization** (one call per chunk, then one over the summaries) was rejected on cost then (79 calls for one file against
an OpenRouter cap of 50/day; *re-costed in slice 7 §13.7: the blocker is now latency, not quota*).

**⚠ OVERTURNED 2026-09-14 — see [the selector](../step1/ask-path.md#13-the-selector-and-the-scenario-matrix-behind-it--decided-2026-09-14). The selector shares the leftover instead: A before B leaves A UNCAPPED, so a large reference starves B entirely, and it biases every code-vs-code comparison by upload order. When A fits, the two rules give the identical answer.** *(The earlier text here — "filling A before B is the right selector rule: dropping part of B is recoverable, dropping part of A loses a statement we never learn exists; the 50/50 split is wrong in principle but `select()` stays broken on purpose" — is the rule that was overturned.)*

### Output length — `max_tokens` needs a real number

Rough count of the full template on the sample pair: §7 (about 18 rows) 1,100 · §10 explanation + §12 corrections 1,000 · every other section 2,400 · **answer total ~4,500**. Thinking
tokens sit on top and are not under our control, so **8,000 is probably not enough** ([Thinking models](../llm/failure-rules-and-limits.md#thinking-models--the-count-is-at-least-four-of-seven)); start at 16,000 and treat
`finish_reason: length` as the signal, not the look of the text. *(Measured later: 24,000, then 32,000.)*

### What slice 4 built — `labpilot/prompts/`

`_ids.py` (`assign_ids`, one running counter per side) · `context.py` (`build_context(chunks, selected)`, the outline plus the kept text) · `instructions.py` (`Instructions`, `FULL` 14
sections, `CORE` 6 sections; later the lean `REPORT`, `SCAN`, `COMPARE`) · `builder.py` (`build_prompt`, `reserve`) · `citations.py` (`Citation`, `find_citations`, `resolve`).
**Chunk ids are assigned at prompt time, not by the chunker:** `chunk_index` restarts at 0 for every file, so a four-file repo would produce four different `B-17`s; `assign_ids` walks
the whole side with one counter (`train.py` ends at `B-40`, `model.py` starts at `B-41`). Nothing in `ingest/` changed.

### Citations — deterministic quoting, not line numbers

The model **cannot count lines**, so asking for one is asking it to guess. **Deterministic quoting**: the model gives a pointer; the machine does the counting; the text shown to the
user is read back from our own file, never from the model. Model writes `[B-17 "count = count + 1"]` → we check B-17 exists and the line is inside it → compute newlines before it +
`chunk.start_line` → `train.py:1203` → display our copy of that line. **Printing line numbers on every line was rejected on cost** (~3 tokens per line ≈ 3,000 tokens, 15% of the
budget, to buy what a quote gives free). `resolve` matches **line by line** (exact match on the stripped line first, then "the line contains the quote"), so indentation is ignored
(the model will not copy leading spaces reliably); when more than one line matches `Citation.unique` is `False` (the finding stands, the line number is a guess between two places).
**The format `[B-17 "…"]` is fixed in the instructions purely so a regular expression can find citations afterwards**: a citation nobody can parse cannot be checked.

### The outline does not scale past Step 0

Listing every chunk header costs ~2,400 tokens for the 96-chunk pair and about **40,000 tokens for a 2,000-chunk repository**, larger than the whole budget; Step 1 must list **files**,
not chunks (done: the outline ladder, slice 7 §12). **⚠ OVERTURNED 2026-09-14 — see [the selector](../step1/ask-path.md#13-the-selector-and-the-scenario-matrix-behind-it--decided-2026-09-14): `select()` should NOT fill A before B (the line that stood here); the leftover is shared.**

### Thinking controls — three hosts, three different shapes

Verified from each provider's own docs on 2026-08-14: there is **no shared field** ("they are all OpenAI-compatible" is true of the message shape and false of this). Google:
`generationConfig.thinkingConfig.thinkingLevel` (`LOW` `MEDIUM` `HIGH`); Mistral: **root** `reasoning_effort` (`"high"`/`"none"`) **and `top_p: 1` beside it**; OpenRouter: **root**
`reasoning: {"effort": …}` (`xhigh`…`none`); Cloudflare: not documented then; Devstral 2 **rejects it** (`400`, `code: 3051`). This file had guessed `thinkingConfig.thinkingBudget` —
that is the **Gemini 2.5** field; Gemini 3 uses `thinkingLevel` and sending both is a 400. **So the code carries two different things, on purpose:** `GeminiProvider` gets a `thinking`
field (nested inside `generationConfig`, cannot merge at the top level) and `OpenAICompatibleProvider` gets a generic `extra_body: dict | None` merged into the payload (inventing one
name for three shapes would be a lie); both default to `None` and are data in `registry.py`. **Two traps:** Mistral answers **HTTP 422** when a model does not accept
`reasoning_effort` (setting it on `glm-5-2` or `devstral-2512` could kill two tiers), and OpenRouter **silently drops** it for some models (no error, no effect, worse than a failure),
so every value stayed unset until one real request proved it. Free measurement: `_usage_summary` on the OpenAI shape also prints `completion_tokens_details.reasoning_tokens`
(mirroring Gemini's `thoughtsTokenCount`).

### `REPORT_MAX_TOKENS = 24_000`, and the tier it deliberately costs

*Corrected 2026-08-14: pinned 16,000 first (the largest value every tier accepts); measurement overruled it.* Limits unchanged (Devstral 2 **16,384** binding · North Mini Code 64,000 ·
both Gemini 65,536), but at 16,000 **both** runs (`FULL`, `CORE`) returned `MAX_TOKENS` — a truncated report is not a worse report, it is not a report at all. So the constraint gave
at tier 5: **24,000, and Devstral 2 can no longer serve a full report** (`_check_fits` raises before the HTTP call, so the loss is cheap). The invariant test says so out loud:
`test_only_devstral_cannot_serve_a_full_report` asserts the unable-list is *exactly* `["Devstral 2"]`, failing if a **second** tier ever drops below the report budget ("a deliberate
loss is pinned; an accidental one breaks CI"). At 24,000 `CORE` finished (`STOP`) and `FULL` still did not. *(Later 32,000; the pinned list is now `("GPT-OSS 120B (Groq)", "Devstral 2")`.)*

### `finish_reason` was promoted to `LLMResult`

*2026-08-14.* It had been logged only; the rule says a logged field is promoted "the moment the UI or the budget validator needs the number", and the slice 4 measurement needs it:
`stop` = finished, `length` = `max_tokens` cut it mid-sentence. It passes the seam test (every provider reports it; `_extract_message` already returned it in both wire shapes) and
defaults to `"unknown"` so no construction site changed.

### What the smoke run writes

`pytest tests/smoke --run-smoke -q` writes into `artifacts/` (git-ignored) one report per run (`2026-08-14_18-30_full_gemini-3.6-flash.md`, `..._core_...md`) plus `..._comparison.md`;
each carries `finish_reason`, chunks sent, prompt tokens, citations written, **citations that resolve**, failed tiers, the answer and the exact prompt. **Read `model` and `tier` before
believing a comparison:** two runs served by different tiers changed the model, not just the prompt — re-run. Thinking-token counts stay in the log, not on `LLMResult` (Google and the
OpenAI shape name them differently): `pytest tests/smoke --run-smoke -q --log-cli-level=INFO`.

### The measurement — five runs, all saved

| Run | prompt | max_tokens | chunks | finish | citations resolve | findings |
|---|---|---|---|---|---|---|
| baseline | bare | 2,000 | 60/96 | cut | ~50% | **10/18** |
| 1 | `FULL` | 16,000 | 63/96 | `MAX_TOKENS` | 1 of 3 | not scorable |
| 2 | `CORE` | 16,000 | 65/96 | `MAX_TOKENS` | 1 of 1 | not scorable |
| 3 | `FULL` | 24,000 | 63/96 | **`MAX_TOKENS`** | 22 of 45 (49%) | not scorable |
| 4 | `CORE` | 24,000 | 65/96 | `STOP` | 67 of 72 (93%) | **9/18** |
| 5 | `CORE` **stuffed** | 24,000 | **96/96** | `STOP` | **73 of 74 (99%)** | **11/18** |

**`FULL` was never scored because it never finished** (cut at §7 at both budgets); its 49% is an artifact of truncation, not citation quality — do not read runs 1 and 3 as evidence
about template length. **Citations are solved** (99% on the stuffed run: deterministic quoting works). **Coverage is the whole problem:** the bare prompt found 10 with two-thirds of
the context, the full template with *all* the context found 11.

### `PROMPT_BUDGET = 26_000` — measured, not chosen

*Recorded 2026-08-14; the first plan "keep `INPUT_BUDGET` at 20,000" was proven wrong by measurement.* At 20,000 the reserve of ~5,300 comes out of the chunks, so side B drops from the
baseline's 10,000 tokens to **7,332** (a 27% cut in evidence), and run 1 would change the prompt *and* delete a quarter of the code. **`INPUT_BUDGET = 20_000` always meant the
*evidence* budget** (no instructions then), so the total grows by the reserve to keep the evidence the same. `PROMPT_BUDGET` lives in `labpilot/prompts/builder.py` beside
`REPORT_MAX_TOKENS` (both belong to the task, not a model); the caller does `select(chunks, budget=PROMPT_BUDGET - reserve(...))`. Measured on the sample pair (96 chunks, A=18, B=78):
baseline 0/0 → 60 chunks (B=42), evidence 14,273 · `FULL` instructions 2,272, reserve 5,336 → 63 (**B=45**), evidence **14,558**, prompt 19,736 · `CORE` 1,846 / 4,910 → 65 (**B=47**),
**14,791**, 19,545. Total request ~19.7K in + 16K out ≈ 36K, far under tier 7's 128K floor. The prompt still lands ~6,000 under budget — `select()`'s 50/50 split wasting side A's
unused half, removed by the slice 7 selector.

### The measured ceiling of one call — 2026-08-14

*The most important slice 4 result: it changed an assumption into a measurement.* Three runs, all `gemini-3.6-flash`, `thinkingLevel: HIGH`, `max_tokens = 24_000`: bare prompt 60/96
chunks → 10 findings, ~50% citations, unfinished · `CORE` 65/96 → 9, 93% · `FULL` 63/96 → cut at §7, 49% · **`CORE` everything stuffed 96/96 → 11, 99%, finished**. **Stuffing the entire
fixture, no retrieval at all, bought exactly two findings** (`pos_class_weight` defined and never called; the unfreeze off-by-one), both needing parts the selector had dropped; the other
**seven** survived perfect context: **retrieval costs ~2, the single call costs ~7.** The continuation "and no prompt fixes the seven" was wrong and is replaced by the next section.
The literature on the long-run limit (**multi-needle decay** — recall falls as the number of facts asked for rises and reasoning over them is worse than retrieving them, [LangChain
multi-needle](https://www.langchain.com/blog/multi-needle-in-a-haystack); **context rot** — accuracy declines as input grows even when the evidence is present and well placed;
**map-reduce wins** — smaller focused calls keep recall) matches our misses (four of seven are Type-3: things B does that A never mentions, a long list late in the context).

~~"One call cannot reliably find many things in a long text. The fix is many small calls, not better sentences."~~ > **CORRECTED 2026-08-17, session 10.** Probe v2 asked **four**
questions in **one** call on 22,753 tokens and recovered seven findings, five of which seventeen runs never found. The accurate version: **one call can only be asked one thing at a
time; the fix is more questions, and small calls are how you ask them without the prompt collapsing.** The literature is right about the long-run limit; it was not the binding
constraint (we asked one question). **The agent is still a requirement, for two *measured* reasons:** (1) each question needs its own pass (`verify`, `find_bugs`, `find_missing`
are three questions, each returning what the others cannot see); (2) discovery needs a precision pass after it (asking for bugs manufactures some; `P1` was ranked first and wrong;
nothing inside a single generative pass can check its own output). *"Step 0's ceiling is about 11 of 18" was also wrong: 11 is where **this** prompt stops, not where one call stops.*

### Why coverage is stuck — diagnosed 2026-08-14

> **Every one of the 11 findings carries an A citation. Every one of the misses has no anchor in A.**

`D1`-`D11` each cite a line of A then a line of B: the model walked **A's list of statements** and checked each in B; it never walked B. The misses against the same test: #14
vocabulary capped at 20,000 (OOV non-trivial), #15 rows dropped when empty after the regex, #16 three layer-norm modules built and never enabled, #17 `requires_grad` passed as an
optimizer param-group key, #18 all-stopword question encodes to the zero vector — **none mentioned in A**; #9 threshold tuned on the split it is reported on and #10b the 12.1-point
train/validation gap — in A, but need reasoning over B's own numbers. The model produced **zero pure column findings** (even #11 stopword masking and #13 cosine similarity were found
only because A said something beside them: `A-6 "excludes padding positions and nothing else"`, `A-9 "r = [u;v;|u-v|;u⊙v]"` — row findings wearing a column finding's clothes).
**Two things in the code explain it, neither "too many rules":** (1) **`CORE` deleted the column-walk instruction** (`FULL` §7: "first every statement A makes, **then every decision B
makes that A never mentions**"; `CORE` §3 only "Biggest effect first"); (2) **`CORE` has no "problems in B alone" section** (#16, #17, #18 had nowhere to be written) — the template that
scored 11 had removed the home of five of the seven misses. The "too many rules" guess was half right (two of our rules cost us) but the direction was backwards: **cutting sections lost
the findings.**

#### What the literature calls this

**Anchoring** (once the model latches onto one category it under-reports the others; fix: constrain each pass to one concern; self-aggregation over 10 runs raised recall **118%**, so a
single pass finds under half; [Augment Code](https://www.augmentcode.com/guides/deep-code-review-recall-vs-precision)) · **single-pass extraction is non-exhaustive** (Google's
[langextract](https://github.com/google/langextract) ships multi-pass: 2 passes → 93% recall, 3 → 96%; L3X recall-first then precision pruning, [Recall Them
All](https://arxiv.org/abs/2405.02732)) · **instruction density has a measured curve and the failure mode is skipping** (IFScale: ~90% adherence at 10 instructions, ~70% at 50, ~40%
at 150; models **drop whole instructions**, middle ones first, [arXiv 2507.11538](https://arxiv.org/pdf/2507.11538)) · **serialising while thinking costs 10-30% of reasoning** but
recovers whenever unconstrained reasoning precedes structured submission ([Capacity, Not Format](https://arxiv.org/html/2606.09410)) · **decomposition beats one large prompt** (DecomP
50.6% vs 36% CoT, [Decomposed Prompting](https://www.emergentmind.com/topics/decomposed-prompting-decomp)).

### The four prompt fixes — BUILT 2026-08-14, not yet measured

*All four were built into `instructions.py`; one grew a second half (see [the A-walk correction](#the-a-walk--the-correction-that-raised-the-prediction)).* (1) **Make the enumeration
positional, not semantic:** `Walk side B's part list from the first id to the last. For EVERY id write one line: B-12 | <a decision this part makes that A never mentions> / B-13 |
nothing. Do not skip an id. Do not merge ids. Write this list before you write any table.` Free recall stops when the answer *feels* complete (why the model stopped at 9, then 11);
a positional walk makes stopping early **visible and countable** (78 ids in, 78 lines out) — the single-call form of the Step 2 loop. (2) **Give the defect scan its own pass, placed
before the comparison** (anchoring is category-level): `PROBLEMS IN B ALONE` back in `CORE`, before the difference table. (3) **Let it think in prose before the table** (the 10-column
table *is* the thinking, premature serialisation). (4) **Delete `_CAUSES`** (~25 lines of examples mid-prompt forcing no behaviour, where IFScale says instructions get dropped).

### The A-walk — the correction that raised the prediction

Writing fix 1 exposed an error in the diagnosis: #9 and #10b were filed as "needs reasoning over B's own numbers — Step 2 work", but both are **stated in A** (`A_paper.md:212` "It is
selected once, at the end of ... applied unchanged to the test set"; `A_paper.md:232` "is 2.1 points. We take this as evidence that the dropout rates ..."). So they are row findings:
**the model walked A incompletely, answering some of A's claims and silently skipping others** — "as much of A as the model felt like doing". **Both walks are positional now**
(costs almost nothing: A is 18 parts against B's 78). > **A miss you have not looked up is not evidence about the model; it is evidence about your scoring.**

### The revised prediction, so it can be falsified

`11 + 2 (#9, #10b — A-walk) + 4 (#14-#17 — B-walk) + 1 (#18 — defect pass) = 18` is the *arithmetic* ceiling, not a forecast; **expect 15-16; at or above 14 the fix works, 11 means the
diagnosis was wrong.** Measure it stuffed (new `CORE` vs the stuffed 11/18 baseline, both 96/96, both tier 1). Before believing the score: **(1) count the walk lines** (B has 78 ids; 40
lines means rule 6 was ignored — a different failure) and **(2) read §6 for the banned comparison** (the two F1 numbers must not share a sentence). *(Result: it was 11 again, and the
walks were empty — see "The prompt fixes were measured, and they failed".)*

### What was actually built

Walk A and walk B positional (`CORE` §2/§3; `FULL` §7 rewritten in place) · defect scan before the comparison (`CORE` §4 ahead of §5) · prose before the table (the walks *are* the prose)
· `_CAUSES` deleted (hints moved inside walk B) · the comparison ban (rule 4: a `NO` pair may not share a sentence anywhere below) · walk completeness (rule 6, repeated in the closing
for recency). **A conflict had to be resolved (the kind IFScale warns about):** rule 1 demands a citation for every statement, rule 6 demands ~78 walk lines mostly "nothing"; rule 1
now carries an explicit exception for walk lines that report nothing (a different pair, rule 6 and `§5`, later deadlocked: instruction bug 1). **`REPORT_MAX_TOKENS` rose 24,000 → 32,000** (the walks add
~96 lines; no further tier lost, the next binding limit is North Mini Code at 64,000). Measured cost: instructions 1,846 → 2,052 tokens, reserve 4,910 → 5,272, chunks selected 65 → 64
(**one chunk for four new sections**; deleting `_CAUSES` paid for most).

### Two prompt rules the runs proved, both general

**1. A forced verdict must be first, and it must also bind the prose after it.** *(Corrected 2026-08-14: the first version misread the artifact.)* §2 demands `YES / NO / CANNOT TELL`
and got it right in every run; §4's `NOT APPLICABLE` **is** the first thing on its line and correct. The failure is the paragraph *after* it, which performs the banned comparison
anyway ("consistent with Side B's observed validation F1 of 0.8262 … lower than Side A's test F1 of 0.851"). Moving the verdict first would change nothing: **a correct verdict does not
constrain the prose that follows it. Ban the material, not the conclusion** — after a `NO` the two numbers may not appear in the same sentence anywhere below. Method lesson: the
recorded diagnosis and the saved artifact disagreed, and only re-reading the artifact caught it. **2. Free recall stops when the answer feels complete:** §3 said "finish this list
completely" and the model stopped at 9, then 11; the fix is to walk the input by id so stopping early becomes visible and countable.

### What Step 0 ships, and where each section goes later

§0-§2 yes → `summarize` ×2 · §3 verdict only (cannot halt the graph) → the **correspondence gate**, a real halt (D78: it compares the two summaries, section 28) · §4 yes, general knowledge only → `find_bugs`, walking files · §5-§6 yes
→ the `result` claims and the answer instruction (**`extract_outcomes` was withdrawn on 2026-11-12, D108, section 31**) · §7 one pass over the given context → `verify` + `find_missing`, one search per row · §8-§10 yes → `diff_choices` +
`explain_divergence` routed to tier 1 · §11 reported only → drives **re-retrieval** · §12 yes → **`propose_fix`** (also not in the library) · §13 yes → `propose_next`. **The template found
two capabilities the library was missing** — `extract_outcomes` (withdrawn 2026-11-12, section 31) and `propose_fix` — to add to [The capability library](../agent/design.md#the-capability-library) at Step 2. **The honest Step 0 limit:**
every `not in context` in §7 may be a false alarm caused by the deliberately bad selector; removing that is what Steps 1 and 2 are for.

