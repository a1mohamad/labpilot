# Full text: Slice 6 — the theory, recorded 2026-09-09

[Docs home](../../README.md)

## Slice 6 — the theory, recorded 2026-09-09

*Session 19 wrote no source on purpose. The lesson came first, the user pushed
back on the cost arithmetic four times in a row, and every push was right. What
came out is a set of **verified provider facts**, a rule about what can and
cannot be batched, and a measurement that slice 6 now owes before it closes.*


### The concept — and why the embedder cannot do this job

**A bi-encoder** — `embed/`, what we already have — encodes the query and the
chunk **separately**:

$$
s(q,d) \;=\; \frac{E(q)\cdot E(d)}{\lVert E(q)\rVert\,\lVert E(d)\rVert}
$$

`q` the query · `d` the chunk · `E` the embedding model. The whole design rests
on one property:

$$
E(d) \;\text{does not depend on}\; q
$$

That is what lets a vector be computed at ingest and stored in Postgres. It is
the strength **and** the weakness: the chunk's vector was made **before the
question existed**, so it must be one fixed summary that is good for every
possible future question.

**A cross-encoder** — a reranker — puts both into **one** sequence:

$$
s(q,d) \;=\; f\big(q \oplus d\big)
\qquad\text{and}\qquad
s(q,d) \;\neq\; g(q)\cdot h(d)\ \ \text{for any } g,h
$$

Self-attention now runs over the query tokens **and** the chunk tokens together,
in every layer. The names are **late interaction** (bi-encoder — they meet only
at the final dot product) and **early interaction** (cross-encoder — they meet
throughout).

**Our own worst miss is the worked example.** Query `D2` is *"gradients are
clipped at a global norm of 1.0"*; the answer is the constant `CLIP_NORM = 1.5`.
In the bi-encoder the word `clipped` and the token `1.5` are in two separate
forward passes weeks apart and **never meet** — codestral ranked it 46th. In a
cross-encoder they sit in the same sequence and attention connects them.

**The non-factorisation is the whole story.** It is why a cross-encoder is more
accurate, why it cannot be precomputed, why it cannot be indexed, and — see
below — why it cannot be batched across queries.


### What batches, and what does not — the rule

> **Batching works when the inputs are independent. It fails when they must be
> joined.**

| operation | shape | batches? |
|---|---|---|
| **embedding** | `E(text)` — one text at a time, independent | ✅ **96 per request**, already built |
| **reranking** | `f(q ⊕ d)` — needs the pair | ❌ not across queries |

This is not a limitation we can engineer around at the API. It follows from the
same factorisation property above.

**Query embedding is therefore not a quota problem**, and the arithmetic says so
plainly. A claim is ~20 tokens:

```
30 claims x 20 tokens  =    600 tokens, ONE request   (MAX_BATCH_SIZE = 96)
one ingest             =  384,000 tokens, 21 requests
```

**The embedding quota only binds at ingest**, which is offline and happens once
per artifact. Slice 1 already built `embed(texts)` and `embed_batches()` for it.


### The provider facts — read from the official docs 2026-09-09

*Every row below is from the provider's own documentation, per the sources rule.
CLAUDE.md previously carried three numbers here that were estimates.*

| | Cohere | Voyage | Cloudflare |
|---|---|---|---|
| `query` field | **one string only** | **one string only** | one string |
| documents per call | **up to 100 per search unit** | up to 1,000 | — |
| free allowance | **1,000 API calls/month**, 10 req/min | **200M tokens**, one-time | **10,000 neurons/day** |
| billed by | **the CALL** | tokens | tokens |
| reranker rate | — | — | **283 neurons / 1M input tokens** |

**Voyage publishes the token formula, and it corrects our own arithmetic:**

$$
\text{tokens} \;=\; \big(t_q \times N_d\big) \;+\; \sum_{i=1}^{N_d} t_{d_i}
$$

`t_q` query tokens · `N_d` number of documents · `t_di` tokens in document `i`.

With our **measured** 229-token average chunk and a ~20-token query:

$$
20 \times 50 \;+\; 50 \times 229 \;=\; 12{,}450 \text{ tokens per 50-chunk call}
$$

CLAUDE.md's budget section assumed **25,000**, from a 500-token chunk that our
corpus does not contain. So the real capacities are roughly double what was
recorded:

```
Voyage       200,000,000 / 12,450  =  ~16,000 calls   (was recorded as 8,000)
Cloudflare   12,450 tokens -> 3.5 neurons
             10,000 / 3.5          =  ~2,850 calls PER DAY   (was ~1,400)
Cohere       1,000 calls/month, and the document count does not change it
```

**A free lever nobody had noticed: Cohere bills per call, up to 100 documents.**
We send 50. **Sending 100 costs exactly the same** and can only raise recall.
On Voyage and Cloudflare it doubles the token cost, so this is a per-provider
choice, not a global one. Slice 8 should test it.


### Two counting errors in this file, now corrected

**1. `r = 5` was wrong.** The budgeting section said a full report does *"~5
retrievals"*, so Cohere would give ~200 reports/month. But the agent design in
the same file says claim extraction yields **~14 claims**, and each claim needs
its **own** search. The `5` came from the *verify batching* line — 5 claims per
**generation** call — which is a different step with a different budget.

> **Batching `verify` saves generation calls. It saves no rerank calls**, because
> reranking happens once per **search**, and batching the answering step does not
> reduce the number of searches.

**2. `14` is itself a guess**, and probably low. The claim-extraction rule *"one
fact per claim"* forbids merging, which pushes the count **up**: *"lr 3e-4 with
cosine decay and 500 warmup steps"* is **three** claims, not one. Re-retrieval
after a `not found` verdict pushes it up again. Nobody has counted the claims in
a real paper — `A_paper.md` is sitting in the repo and counting it costs nothing.

**So the honest form is `r = N + 1`, with `N` unknown until Step 2 exists.**


### A process failure worth more than the numbers

Asked *"how many rerank calls per report?"*, I produced **four different answers
in four messages** — 5, then 14, then ~4, then 1–2 — each time quietly changing
an assumption without saying it had changed. Only the first came from this file;
the rest were invented and presented in tables, which made guesses look like
measurements.

The correct answer was available from the start: **"that cannot be counted
until the agent exists."**

> **When a question has no answer yet, say so. Do not produce a number and then
> defend it.** A number with no derivation is worse than a blank, because a blank
> cannot be quoted back six weeks later.

And the deeper fix, which is what actually resolved it: **stop trying to
estimate `N`, and find the provider whose budget makes `N` stop mattering.**
That answer needed no estimate at all.


### Four ways to spend less on reranking — from the literature, 2026-09-09

**1. Run the model yourself, and batching returns.** A cross-encoder cannot merge
two queries, but it *can* score many pairs in one forward pass. Published
figures for our exact candidate, MiniLM-class (22M): **100 documents in 50–80
ms**. The *"one call per query"* limit is an **API billing shape**, not a model
limit. This is the single largest lever available to us.

**2. Fan-out, merge, deduplicate, then ONE rerank.** The standard production
pattern: many sub-queries retrieve in parallel, all candidates go into one pool,
duplicates are removed, and a **single** rerank runs against the *original*
question.

> **The rule that decides whether it applies: do all these searches serve ONE
> answer, or N separate answers?**

For LabPilot it applies to `answer_question` and **not** to `verify` — merging
`verify`'s candidates destroys the claim-to-chunk mapping, and per-claim
verdicts are the whole point of that capability.

**3. Gate it — skip reranking when the search is already sure.** Measured in the
literature at **15–80% compute saved**, with equal or better accuracy. And the
finding that matters more than the saving: **reranking can make results worse**
when the first-stage ranker was already confident and correct.

The signal is free for us, because the similarity matrix already holds every
score. The natural gate is the **margin** between the top two:

$$
m \;=\; s_{(1)} - s_{(2)}
\qquad
m > \tau \;\Rightarrow\; \text{skip} \qquad m \le \tau \;\Rightarrow\; \text{rerank}
$$

`τ` is **not chosen — it is calibrated**, on `queries.json`, exactly as the
correspondence gate's threshold must be.

**4. Adaptive depth.** Rerank fewer candidates for an easy query. Interacts with
the Cohere-bills-per-call finding above, so it is provider-dependent.


### The decision ladder

```
1. Does the WHOLE artifact fit the prompt budget?
     YES -> send it all. No search, no rerank.
     (CLAUDE.md's existing rule: "add it up; if it fits, send it all")

2. Too big -> vector search, take the top SEARCH_LIMIT (50).
     Cheap: one embed call plus arithmetic. No provider is touched.

3. Is the winner obvious?   margin between the top two scores
     clear   -> SKIP the reranker
     close   -> RERANK

4. Send the final chunks.   How many? -> MEASURED, see below.
```

**Step 2 needs one correction that is easy to get backwards.** The reason we cut
50 down to ~10 is **not** the budget:

```
50 chunks x 229 tokens  =  11,450 tokens
evidence budget         =  ~24,000 tokens      it FITS
```

The reason is **quality**, and the two forces pull opposite ways: sending 50
gives `recall = 0.994` but dilutes the signal (`alpha = f/s`, this file's own
chunking math) and invites *lost in the middle*; sending 10 gives a sharper read
of `recall = 0.930`. **Which wins is unmeasured.**


### THE MEASUREMENT SLICE 6 OWES BEFORE IT CLOSES

*Added at the user's request, 2026-09-09. Slice 6 previously ended at "the top
50 become the right top 10, and skip still works", which is a behaviour, not a
decision.*

Run it with the **local ONNX model**, which costs nothing and can be repeated.
Cache every result to disk, as `score_hybrid.py` already caches embeddings.

| # | Measure | Decides |
|---|---|---|
| 1 | `r@10` and `MRR` before vs after reranking, **per corpus and per embedder** | does reranking help us **at all** |
| 2 | **how many chunks to send** — top 5 / 10 / 20 / all 50 | the `SEARCH_LIMIT` -> prompt cut |
| 3 | the **gate**: how often is the margin already decisive, and does skipping cost anything | whether `tau` is worth having |
| 4 | **`wRRF` fusion re-measured WITH the reranker on** | whether slice 5's gain survives |

**Report the headroom captured, not the raw gain**, because a raw `+0.03` means
nothing without knowing how much was available:

$$
\text{captured} \;=\;
\frac{\text{r@10}_{\text{after}} - \text{r@10}_{\text{before}}}
     {\text{r@50} - \text{r@10}_{\text{before}}}
$$

**And a free check on the instrument: `r@50` must not move.** A reranker only
re-orders what it was given. If `r@50` changes, the measurement is broken — the
same class of sanity check that caught the identical-vectors bug in slice 4.

**Three rules carried forward from slice 5, unchanged:**

- **This fixture may REJECT, never CONFIRM.** The headroom at `k=10` is only
  `0.994 - 0.930 = 0.064`, so **one query on the 45-query fixture is 35% of it**.
  A tie means keep the code and let slice 8 decide.
- **Name the corpus AND the embedder beside every number.**
- **Judge a method by how many independent ways it was shown better**, never by
  its best single number.

**A number in this file to verify while running measurement 1.** START HERE
reports `recall@1 0.645`, and the slice 5 comparison table reports `MRR 0.645`
— the same value. Those cannot be equal: `MRR > r@1` whenever any query ranks
2nd-5th, and `r@5 = 0.871` proves some do. So the `recall@1` label is almost
certainly the MRR value, and the true `r@1` is **lower**. `score_hybrid.py`
already reports both separately, so one run settles it.


### THE CHAIN ORDER STAYS — and what could change it

**Chain 3 is NOT reordered.** *(The user's decision, 2026-09-09.)* It stays
Cohere -> Voyage -> Cloudflare -> `ministral-3b` -> `skip`, on the rule that
still holds: **spend the bucket that expires anyway, bank the one-time grant.**

**But the quota shape argues differently once reranking is per-query**, and that
argument is recorded here so slice 8 can weigh it:

```
per REPORT   Cohere's 1,000/month is ample          -> the file's order is right
per QUERY    Cohere      1,000/month  =  smallest budget by far
             Voyage     ~16,000 once
             Cloudflare  ~2,850/DAY   =  the largest renewing budget
             local ONNX   unlimited, and it BATCHES
```

**A candidate order for slice 8 to test against the current one:**

```
local ONNX  ->  Cloudflare  ->  Voyage  ->  Cohere  ->  skip
```

That is the opposite of today's chain, and it is **a proposal with evidence, not
a decision**. Two things could kill it: quality (slice 8 measures it, and the
current order has never been measured either), and the **512MB budget** — the
local model is ~120MB resident, which this file deliberately excluded from the
container. If reranking is genuinely per-query, that exclusion is worth
re-checking at Step 3.


### What slice 6 may NOT conclude

| may conclude | may NOT conclude |
|---|---|
| whether reranking helps our data | **which provider is best** — slice 8 |
| roughly how much headroom it captures | that the chain-3 **order** is settled |
| how many chunks to send | that fusion is dead — retest it **with** rerank on |
| whether the gate is worth having | the real value of `r` — that needs Step 2 |


### Notes for the code, before a line is written

- **`rerank/` is an ADAPTER.** It must be added to `ADAPTERS` in
  `test_architecture.py`, or the build fails on *"belongs to no layer"*. It may
  then import only `tokens` and `_text` — so it **cannot** see `SearchHit`, and
  its signature is plain strings in, an order out:
  `rerank(query: str, documents: Sequence[str]) -> tuple[int, ...]`. The caller
  in `api/` owns the translation, because entry is the only layer allowed to
  import both.
- **`test_error_boundaries.py` will fire** the moment `api/` imports `rerank`.
  That is the guard working. Catch the error and map it to a status, or name it
  in `ALLOWED_TO_ESCAPE` with the reason — never delete the test.
- **A reranker must NOT inherit `HTTPProvider`.** An old slice-1 note predicts it
  will; that note is **stale**. `llm/base.py` is a *completion* template
  (`tier`, `context_window`, `max_output_tokens`, `finish_reason`) and a
  reranker would fill four fields with fiction — the exact argument that kept
  the embedder out of it. Follow the `embed/` precedent, and write no `base.py`
  until the second reranker exists.
- **Tests must never call Cohere.** Its 1,000/month is one bucket shared with
  chat and embed, and Cohere is the rerank primary. Use the local ONNX model,
  installed in `requirements-dev.txt` only —
  `test_no_runtime_requirement_would_blow_the_memory_budget` reads
  `requirements.txt` alone, so a heavy dev dependency is allowed by design.
- **Probe cheapest first** when learning each wire shape: Cloudflare (~3.5
  neurons), then Voyage (1 of ~16,000), and **Cohere last** (1 of 1,000).
- **The 510-token trap is closed**, and the numbers above depend on it. Cohere
  splits any document over ~500 tokens and bills each piece. The 2026-09-05 cap
  fix put **0 of 4,889** chunks over the cap; before it, 43 of 1,094 were over
  and every rerank budget in this file was wrong by up to 3x.

Sources for the provider facts: Cohere Rerank API reference and rate-limits
page, Voyage reranker documentation and FAQ, Cloudflare Workers AI pricing.
