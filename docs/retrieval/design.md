# Retrieval design

[Docs home](../README.md)

## Retrieval Design — recorded 2026-08-13

*Decided during the RAG lessons of session 4, before slice 3 was written. The
chunking half is built in slice 3; the query half arrives with the planner at
Step 2. Both are recorded now because they change what slice 3's data structures
must carry.*

### The user's question is not the search query

The single most important retrieval rule in this project, and the one that
textbook RAG diagrams omit:

```
❌ search text: "Compare these and explain why the results diverge."
✅ search text: "learning rate of 3e-4 with cosine decay"
```

The failure has a name: **query–document asymmetry**. A question is a *request*;
a chunk is a *statement*. Their meanings are genuinely different, so their
embeddings are genuinely far apart. The embedder is not broken — it was asked the
wrong thing.

Worse, a vague query attracts *generic* text. `README.md` saying *"this project
compares our results with the paper"* outscores `train.py:6` on the question
above, and the one line that explains the divergence is never retrieved.

**So a naive single-search RAG would fail at LabPilot's core task. That is a
first-class reason this project is an agent and not one call.**

The rule that replaces it:

> **Search with text that looks like the thing you want to find.**

### Three query sources — cheapest first

Something must produce specific query text. Three things can, and the planner
picks by capability, never by habit:

| Source | LLM cost | Runs | Used by |
|---|---|---|---|
| **A fixed checklist we write** | **none** | never | `find_bugs`, code-vs-code |
| **The other artifact's claims** | 1 call | **once per artifact** | paper-vs-code |
| **LLM query expansion** | 1 call | **once per turn** | vague open questions |

Claim extraction is *not* free — it is an LLM call. It is cheaper only because
the claims are stored in graph state and reused by every later turn, while
expansion pays again on every turn.

This obeys the existing budgeting rule: *plan with rules before spending an LLM
call*. Only reach for expansion when the first two do not fit.

> **Row 1 was narrowed on 2026-09-09.** The fixed checklist is **machine-learning
> vocabulary**, so it cannot serve a physics paper or a C++ solver — which this
> project's own domain-neutrality rule requires. The checklist becomes a *hint*
> inside a generated prompt rather than the query list itself. See
> [the fixed checklist is domain-locked](#the-fixed-checklist-is-domain-locked--corrected-2026-09-09).

### Query source is a field on the capability, not a step in front of everything

**Rejected: running query expansion on every request.** Two reasons.

1. **Query drift.** A specific question is already a good query, and rewriting it
   can only lose. *"What learning rate does train.py use?"* expands into scheduler,
   warmup and weight-decay queries the user never asked for, and the real answer
   ends up buried in noise.
2. Several capabilities need no semantic search at all — `summarize` wants the
   README and the file tree, `find_bugs` wants a checklist.

So each capability declares **where its queries come from**, exactly as it already
declares how many artifacts it needs. The planner knows which capability is
running, so the routing costs nothing — no classifier, no extra call.

| Capability | Query source |
|---|---|
| `summarize` | none — structural (README, file tree, file headers) |
| `find_bugs` | fixed checklist |
| `verify` | the paper's claims |
| `find_missing` | the code's decisions |
| `answer_question` | expand only when the question is vague |

**Tune this by measurement, not by taste.** Run the same question with the raw
query and the expanded query, and look at which chunks come back. That is the
honest way to tune retrieval, and it will be done many times.

### Claim extraction — how side A becomes queries

One LLM call over the method section — no retrieval, the section is small.
Three rules decide whether it works:

1. **A claim must be checkable against code.** *"learning rate is 3e-4"* yes;
   *"our method is more efficient"* no. Read method, training setup and
   experiments; skip abstract, introduction and related work.
2. **One fact per claim.** *"lr 3e-4 with cosine decay and 500 warmup steps"* is
   **three** claims. Merged, a partial match reads as a match and two real
   mismatches disappear. **Detail merged at extraction time can never be
   recovered later — this is the main way a comparison system quietly misses
   things.**
3. **Every claim keeps its source tag** (`[§4.1]`), which travels into the
   retrieval, the finding and the report. This is what makes the citation rule
   possible.

Output a fixed shape (JSON) so the next node parses instead of guessing. It is a
structured task, not a reasoning task, so it belongs on a cheap tier.

### Code vs code uses a checklist, not claims

The agent design below assumes a paper. **Code-vs-code has no prose claims**, so
a fixed checklist of ~12 topics replaces them, searched against **both sides in
parallel**:

```
optimizer and learning rate · model architecture · data preprocessing ·
train/validation split · learning rate schedule · epochs and batch size ·
loss function · augmentation · regularization and dropout · random seed ·
evaluation metric · class imbalance handling
```

12 topics × 2 sides = **24 searches and zero LLM calls** — a search is an
embedding plus a lookup. Then compare topic against itself (A side vs B side,
never topic vs topic), batched ~5 topics per call.

A full 2×4,000-line notebook comparison therefore costs about **6 generation
calls**: 1 to locate the reported results, 3 to compare 12 topics, 1
`explain_divergence`, 1 `propose_next`.

### The fixed checklist is domain-locked — corrected 2026-09-09

*The user asked whether we could generate queries with an LLM call instead of
using a fixed list, "cuz variaty of user question is very much". Checking that
question against the checklist above found a real contradiction in this file.*

**Read the twelve topics again:**

```
optimizer and learning rate · model architecture · data preprocessing ·
train/validation split · learning rate schedule · epochs and batch size ·
loss function · augmentation · regularization and dropout · random seed ·
evaluation metric · class imbalance handling
```

**Every one of them is machine learning.** Now read this file's own rule, earned
when the comparison template was rejected twice for exactly this:

> **LabPilot is not MLPilot.** The design must survive a physics paper vs a C++
> solver, a statistics paper vs an R script, two notebooks in any field.

For a C++ solver, *"optimizer and learning rate"* retrieves nothing, and the
whole code-vs-code path silently degrades to twelve searches that match noise.
**The checklist breaks the domain-neutrality rule, and it did so unnoticed
because the only fixture we have is a machine-learning one** — the same
single-fixture blindness that
[slice 5 measured](../step1/keyword-search.md#slice-5-measured--2026-09-07-vector-ships-wrrf-is-a-named-candidate)
on a different question.

### The decision — generate the topics, with a fixed instruction

*(The user's call, 2026-09-09. Step 2 work; nothing is built at Step 1.)*

**The checklist stops being the query list and becomes a *hint* inside a prompt.**
One LLM call, on a **cheap tier**, produces the topics that actually matter for
the artifacts in front of it.

```
FIXED, versioned instruction   +   a generic topic list as a HINT
                               +   the artifact outline
        |
        v   one call, cheap tier (Flash-Lite: 500/day, Gemma: 14,400/day)
        v
   the topics for THIS comparison, in THIS domain
```

**Three things make this safe rather than loose, and all three are required:**

1. **The INSTRUCTION is fixed and versioned**, even though its output is not.
   That is the same discipline the default prompt already has — *"version the
   default prompt, it is a retrieval query"* — applied one level up. What
   varies is then the model's reading of one pinned question, not a prompt
   somebody edited.
2. **Log the generated queries beside the report.** This is the part that
   restores comparability, and it is not optional. Our chain **falls back**: if
   tier 1 is spent, tier 6 answers, and a *different model writes different
   queries*, which retrieve *different chunks*, which produce a *different
   report* — with no error anywhere. Logging the queries turns that from a
   mystery into a line you can read. Same reasoning as saving the exact prompt
   beside every answer in `artifacts/`.
3. **Keep a fixed fallback list.** If the generation call fails, the pipeline
   still runs — degraded, like `skip` in the reranker chain.

**Cost: one call out of roughly ten per report, on a pool that cannot run out.**
About 10%, and it is what makes the tool work outside machine learning at all.

**`find_bugs` is the exception and should stay mostly fixed.** Its checklist is
not about matching a domain — it is about **coverage** of general programming
mistakes (a missing `zero_grad()`, swapped arguments, no seed, a test loader
that shuffles). That knowledge lives in the model's weights already, so the list
is there to stop the model stopping early, which is the failure
[the walk instruction](../step0/prompt-experiments.md#the-lean-rewrite-measured-2026-08-17-session-10) exists
to prevent.

### And it must be MEASURED, not assumed

*Recorded at the user's request: "i dont know we need to take measurement on
them." That instinct is right, and this file has no business shipping a query
strategy on an argument.*

**The measurable question:** do generated queries find the same evidence the
hand-written ones find?

We already own the instrument. `EXPECTED.md` lists 18 divergences with their
line numbers, and `queries.json` holds 17 hand-written queries whose ground
truth is stored as line numbers so it survives re-chunking.

```
baseline    the 17 hand-written queries   ->  recall over the answer key
candidate   generate queries from A_paper.md with a cheap tier
            -> recall over the SAME answer key
```

**Score coverage, not wording.** The question is not whether the generated query
reads well — it is *how many of the known divergence locations are reachable by
at least one generated query*. A generated set that reaches 16 of 18 beats a
hand-written set that reaches 14, whatever the sentences look like.

**Four things this measurement must record, or it repeats old mistakes:**

- **Which model wrote the queries.** A strong tier and a weak tier will differ,
  and the chain can serve either. Score at least two tiers.
- **Run it twice on the same input.** At `temperature: 0` the queries should be
  identical; if they are not, comparability is worse than assumed and the
  logging in point 2 above becomes the only defence.
- **Both corpora**, and name the corpus beside every number — `quora_siamese`
  is machine learning, and the whole point of this change is the domains it is
  not.
- **The honest limit up front:** neither fixture is a physics paper or a C++
  solver, so this measurement can show the generated set is *no worse* on ML
  code. It **cannot** show it works outside ML. That needs a third fixture, and
  a third fixture is cheap — queries and answer keys cost no quota.

**It spends generation quota**, unlike every other Step 1 measurement, because
query generation *is* a generation call. Two tiers × two corpora × two runs is
8 calls — affordable on Flash-Lite's 500/day, and it must not be run on a
20/day Flash tier.

### One similarity matrix, three readings

Compute `s_ij = sim(E(c_i), E(d_j))` once — claims of A against chunks of B —
and read it three ways:

$$
\text{row } i:\ \max_j s_{ij}\ \text{low} \;\Rightarrow\; \textbf{verify: the paper says it, the code does not do it}
$$

$$
\text{col } j:\ \max_i s_{ij}\ \text{low} \;\Rightarrow\; \textbf{find\_missing: the code does it, the paper never says it}
$$

$$
\max_{i,j} s_{ij}\ \text{and the distribution of } \max_j s_{ij} \;\Rightarrow\; \textbf{the correspondence gate}
$$

**Rows find broken promises. Columns find hidden choices. The whole matrix
answers whether these two artifacts correspond at all.** Three products, one
computation — the gate was already known to be free (**REPLACED 2026-10-29 by D78: the gate now reads the two summaries, section 28**), and `find_missing` is free
for the same reason.

This matters because **most divergence comes from what the paper never says**,
not from a stated value being wrong. The column reading is the one that finds it.

### `find_bugs` is a scan, not a search

**You cannot search for a bug, because you do not know what it is yet.** Search
needs a query; a bug has no query. So `find_bugs` optimises for **coverage**, not
relevance:

```
one small file  →  send the whole file, no retrieval at all
a repository    →  walk the files that matter (model, training loop,
                   data pipeline, loss) and check each in turn, batched
```

And the honest limit, which the product must state rather than hide:

| Findable with **1** artifact | Needs **2** artifacts |
|---|---|
| `optimizer.zero_grad()` missing | `lr=1e-3` should be `3e-4` |
| `criterion(target, output)` — arguments swapped | batch size should be 256 |
| `model.eval()` / `torch.no_grad()` missing in validation | should be cosine, not StepLR |
| `shuffle=True` on the test loader | 500 warmup steps missing |
| no random seed; test data leaking into training | |

The left column is wrong against *general programming knowledge*, which lives in
the model's weights. The right column is only wrong *relative to the paper*.
**With one artifact the honest output is "this is unusual", never "this is
wrong".** That asymmetry is why two artifacts stays the headline.

**Retrieval never finds a typo.** Retrieval puts code in front of the model;
judging is the model's job. `lr=1e-3` and `lr=1e-4` have near-identical
embeddings.

### Stuff, do not retrieve, when the artifact is small

**RAG exists because something does not fit. When it fits, retrieval is not
neutral — it is harmful**, because a bad retriever can hide the buggy line.

```
≲ 8,000 tokens (one notebook)   →  send all of it. No retrieval.
≳ 20,000 tokens (a repo, two big notebooks)  →  retrieve
```

**Those two numbers left a hole, and the hole is the interesting part.**
*(Fixed 2026-08-14, after the user asked what happens between 8,000 and
20,000.)* The real test is not the size of a file. It is:

$$
t(A) + t(B) + t(\text{instructions}) + T_{\text{out}} \;\le\; B_{\text{in}}
\;\Longrightarrow\; \textbf{stuff}
$$

**8,000 was only a shortcut for the common two-artifact case** — two files of
8,000 plus instructions still fit under 20,000. So the middle zone depends on
how many artifacts there are, not on how big one of them is:

| Artifacts | Each | Total | Do |
|---|---|---|---|
| one | 12,000 | 12,000 | **stuff** — it fits |
| two | 12,000 | 24,000 | **retrieve** — it does not |
| two | 8,000 | 16,000 | **stuff** |

**Add up everything you would send. If it fits, send it all.** Size thresholds
are a shortcut, never the rule.

*Already true in the code:* the dumb selector stuffs by accident — when a side
is smaller than its half of the budget, nothing is dropped.

Sizing rule, using the existing `chars / 3` estimator: 4,000 lines of Python
≈ 160,000 chars ≈ **53,000 tokens**, so two such notebooks ≈ 107,000 tokens —
a genuine retrieval case.

### The knowledge split — why a vague question still works

For an open question like *"why does my model diverge in training?"*, the query
problem is really a **knowledge** problem, and it resolves cleanly:

$$
\text{answer} \;=\; \underbrace{\text{what usually causes this}}_{\text{model weights}} \;+\; \underbrace{\text{what YOUR code does}}_{\text{retrieval}}
$$

Ask the model for the known causes first (learning rate, gradient clipping,
`log(0)`, normalization, initialization, mixed-precision overflow), then search
for each one. Six sharp queries out of one vague question. **Neither source
answers alone.**

Also **route by question type**: a training question always fetches the training
loop, the optimizer and the loss, whatever their scores. Cheap insurance against
a bad search.

#### Six queries, ONE rerank — the half this section was missing

*Completed 2026-09-09. "Six sharp queries out of one vague question" is the
technique the literature calls **query fan-out**. This file described the
fan-out and never said what to do with the six result sets.*

**Merge them, deduplicate, and rerank ONCE against the ORIGINAL question.**

```
one vague question
  -> 6 sub-queries         (one cheap LLM call)
  -> 6 searches            (cheap: one embed batch + arithmetic, no provider)
  -> ONE pile: 6 x 50 = 300 candidates
  -> deduplicate           -> ~180 unique
  -> ONE rerank call, query = the ORIGINAL question
  -> top k -> one answer
```

**6 searches, 1 rerank call.** The industry advice is explicit that the rerank
must happen *after* the fan-out, because fanning out floods the pool with
loosely-related chunks that then crowd out the good ones.

**The rule that decides whether fan-out applies at all:**

> **Do all these searches serve ONE answer, or N separate answers?**

| capability | fan-out? | why |
|---|---|---|
| `answer_question` | ✅ | one question, one answer — merge and rerank once |
| `explain_divergence` | ✅ likely | it builds one story out of many findings |
| **`verify`** | ❌ | N claims need N **separate verdicts**; merging destroys the claim-to-chunk mapping, which is the whole point of the capability |
| `find_missing` | ❌ | it reads the **columns** of the similarity matrix — no search |
| `find_bugs` | ❌ | a coverage scan, not a search |
| `summarize` | ❌ | structural — README, file tree, headers |

**So fan-out is a real saving on open questions and NOT on the flagship path.**
It does not solve the rerank budget, because `verify` is where `N` lives. The
thing that makes `N` stop mattering is a reranker with no call count — see
[the slice 6 theory](../step1/reranking.md#slice-6--the-theory-recorded-2026-09-09).

