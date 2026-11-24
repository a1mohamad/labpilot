# Full text: THE STEP 1 CLOSING PASS — 2026-09-19, and it asked one question

[Docs home](../../README.md)

### Slice 8 decides the embedder AND the reranker — recorded 2026-08-28

> **It now decides a third thing: exact vs HNSW.** Added 2026-09-05 — see
> [slice 8's job grew](../../step1/vector-store.md#slice-8s-job-grew--three-measurements-not-one).

*Written at the user's request, before the second fixture exists, so the rule
cannot be bent after the numbers arrive.*

Every embedder number in this file comes from **17 hand-written queries over one
Python file**. That is enough to pick a **default** and not enough to pick a
**policy** — this file already says slice 1 *"picks a default, not a policy"*.
Slice 8 is where both orders stop being provisional.

| | measured today | slice 8 must have |
|---|---|---|
| queries | 17, one author, one file | **a new set, ~50+, written against several projects** |
| corpora | `B_train.py` alone | **several real repositories, more than one language** |
| embedders scored | 5 | the same 5, **plus `gemini-embedding-2`** |
| **rerankers scored** | **zero** | **all four, plus the skip case** |

**The reranker order has never been measured at all, and that is the bigger
hole.** Chain 3 is ordered by *quota shape* — spend the bucket that renews, bank
the one-time grant. That is a good tie-breaker and it is **no evidence** that
they rank alike. Slice 6 builds reranking; **slice 8 is where its order stops
being a guess.**

**The decision rules, fixed now so a later number cannot bend them:**

1. **Rank the embedder on recall@10, not recall@5.** The pipeline retrieves 50
   and reranks to 10. Reranking fixes ordering; it can never recover a chunk
   retrieval did not return.
2. **A model that cannot be indexed is not a candidate**, whatever it scores —
   the pgvector 2000-dimension ceiling is a hard gate, not a preference.
3. **Rank by the resource that runs out**, not only by the score.
4. **A query must never contain the identifier it is looking for**, or the test
   measures string matching and everything scores ~100%.
5. **Score with the answer key; never write the queries from it.** Scoring is
   not leakage. Adding a target because a model missed it is.

**Cohere is a backup for embedding, and that is now a decision, not a
finding.** *(User's call, 2026-08-28.)* `embed-v4.0` wins MRR and ties perfect
recall@10, and it still must not hold a corpus: its 1,000 calls/month is one
bucket shared with rerank, and Cohere is the reranker primary. A corpus embedded
there spends the rerank budget on every query for as long as the corpus lives.
It stays reachable, and it is entered only when the models above it are gone.

**What this section does not decide.** The `MIGRATION` order is not rewritten
today on the strength of one 17-query fixture, however good Google's numbers
are. Google's *storage* question belongs to slice 4, its *ingest speed* to the
routing rule, and its *ranking* to slice 8. **Three separate questions, three
separate slices** — collapsing them is how a default becomes a policy without
anyone deciding it.


### A parallel track, not a slice

Both are data, not code, and block nothing:

1. **The second sample pair** — a different domain, a different language. It must
   exist **before slice 8**, or Step 1 ends without knowing whether the system is
   quora-shaped.
2. **The impact column in `EXPECTED.md`** — owed from Step 0, costs no requests.


### Explicitly not Step 1

Claim extraction, the planner, per-capability query sources, the correspondence
gate, LangGraph, MCP, web search. **All Step 2.** Keeping them out is what lets
Step 1 finish.


### Time estimate, honestly

Step 0 took **eleven sessions for five slices**. Step 1 has nine, and three of
them carry heavy teaching, because this is the first of
[the four gaps](../../rules/teaching-and-communication.md#the-four-gaps-are-the-whole-point--teach-them-hardest-of-all)
and the rule there is to go **slower**, not faster. Slices 1, 4 and 6 will each
take more than one session: the lesson first, then the code.

**Expect 10 to 14 sessions.** And treat eight as the *shape*, not a promise about
size — Step 0 was planned as five slices and stayed five, but every one of them
grew larger than planned.


### Slice 1 — what the embeddings endpoint really does, measured 2026-08-20

*Mistral's docs site is JavaScript-rendered, so the API reference could not be
fetched. The endpoint was probed directly instead — four requests, no meaningful
quota. The probe script is in the session scratchpad.*

| Question | Answer |
|---|---|
| does `input` take a list? | ✅ yes; each item returns `{embedding, index, object}` |
| dimensions | `mistral-embed` **1024** · `codestral-embed` **1536** |
| `output_dimension` | ✅ **works on `codestral-embed`** — asked 512, got 512 |
| `input_type` / a query-vs-document flag | ❌ **does not exist** |
| unknown fields | **rejected — `422 extra_forbidden`** |
| rate headers on a 200 | `x-ratelimit-limit-req-minute: 60`, so 1 request/second |


#### The two models disagree about normalization — so we must normalize

```
mistral-embed        norm = 1.000015    already unit length
codestral-embed      norm = 0.993116    NOT unit length
codestral @ 512      norm = 0.920005
```

**Trusting the provider would have been silently wrong.** `mistral-embed` looks
fine, `codestral-embed` does not, and the difference is small enough that no
error would ever be raised — every cosine score would simply be a little off.

So every vector leaving `labpilot/embed/` is normalized **by us**, once, before
it is returned. Then `cos(u, v)` is a plain dot product everywhere downstream and
nothing later has to remember.

> **Never assume a provider returns unit vectors. Measure the norm.** It is one
> line, and it is the difference between cosine and "nearly cosine".


#### Mistral rejects unknown fields, which is the good failure

`input_type: "query"` returned **422 `extra_forbidden`**. Two consequences:

- There is **no query/document asymmetry parameter** here, unlike Voyage
  (`input_type`), Cohere (`search_query` / `search_document`) or E5/BGE (a text
  prefix). One less thing to get wrong on this provider — and one more thing to
  check when the migration ever moves to another.
- A typo in our payload **fails loudly**. OpenRouter silently drops unknown
  fields, which is the same mistake with no error. Prefer the provider that
  refuses.


#### `output_dimension` is real, and the model is Matryoshka-trained

Both calls below embedded the **same text**, so the comparison is honest:

```
1536 dims  ->  norm 0.993116
 512 dims  ->  norm 0.920005
```

If every dimension carried equal information, keeping one third of them would
leave about `sqrt(1/3) = 0.577` of the length. Instead:

$$
\left(\frac{0.920005}{0.993116}\right)^{2} = 0.86
$$

**The first 512 dimensions hold ~86% of the vector's energy, not 33%.** That is
the signature of **Matryoshka Representation Learning** — early dimensions carry
the meaning, later ones refine it.

Three things follow, and the third is the one that matters:

1. Truncating is a **gentle** trade, not random damage.
2. **86% of the energy is not 86% of the retrieval quality.** Those are different
   quantities. Only recall@k measures the real cost.
3. It is a **recorded lever, not a slice 1 decision.** If 1536-dim storage ever
   hurts, `codestral-embed` can be asked for 1024 — the same width as
   `mistral-embed`, so one pgvector column type serves both.

**But same dimension is not the same space.** Two different models at 1024 dims
still cannot be compared. `output_dimension` solves the **storage** problem, never
the **mixing** problem — every row still carries `embedding_model`, and a query
must never cross models. It also does **not** help speed: the 50,000 tokens/minute
limit counts *input*, so asking for fewer output dimensions changes nothing.


#### The design decisions this settled

| Decision | Answer | Reason |
|---|---|---|
| inherit `HTTPProvider`? | **no** | it is a *completion* template — `tier`, `context_window`, `max_output_tokens`, `finish_reason`. An embedder would fill four fields with fiction |
| a `base.py` for embedders? | **not yet** | one implementation. It is earned when the Google embedder lands (slice 1b) |
| what is reused | **`truncate` only**, promoted to `labpilot/_text.py` | two packages now read it — the same precedent as `estimate_tokens` moving to `labpilot/tokens.py` |
| error type | **`EmbeddingError`**, built by us | one error vocabulary per layer; `error_from_response` returns `LLMError` and stays in `llm/` |
| the registry name | **`MIGRATION`**, never `CHAIN` | a migration order is not a fallback loop. Calling it `CHAIN` invites the loop that must never exist |
| ordering of results | **sort by `index`** | never trust position in `data`. A silent shift puts every vector on the wrong chunk |


#### The failure branches, all real

`ValueError` for a caller's bug, `EmbeddingError` for the provider — the existing
rule, applied at a new layer.

| Failure | Raise |
|---|---|
| empty list, or a blank string | **`ValueError`** |
| `MISTRAL_API_KEY` missing · `RequestException` · non-200 · non-JSON | `EmbeddingError` |
| `len(data) != len(texts)` | `EmbeddingError` — a length shift is silent and total |
| dimension ≠ the declared `dim` | `EmbeddingError` — this is the mismatch detector Chain 2 asks for |
| a zero vector | `EmbeddingError` — it cannot be normalized, and it is finding #18 in our own fixture |


### The slice 1 measurement, and its decision rule written first

**Two questions, not one**, and the second is the more important:

1. Which model — `codestral-embed` or `mistral-embed`?
2. **Does retrieval work at all on this data?** If recall@5 is under ~50% for
   *both*, the model is not the problem — chunking or the query text is, and a
   third model would teach nothing.

**Ground truth:** ~15 pairs of *(query text, the line in `B_train.py` that answers
it)*, in `data/samples/quora_siamese/queries.json`. Queries are `A_paper.md`
claims, because claims are the real query source; the B-only findings get a short
checklist phrase instead. Ground truth is stored as a **line number** and resolved
to whichever chunk contains it, so the file survives any change to chunk
boundaries.

$$
\text{recall@}k = \frac{1}{|Q|}\sum_{q} \mathbb{1}\big[\,r_q \le k\,\big]
\qquad
\text{MRR} = \frac{1}{|Q|}\sum_{q} \frac{1}{r_q}
$$

`r_q` is the rank of the correct chunk for query `q`.

**The decision rule, fixed before any number exists:**

> **`codestral-embed` wins only if its recall@5 is at least 10 points higher.**
> Otherwise use `mistral-embed` — 1024 dims, 400× the token rate, one model
> everywhere.

Using `EXPECTED.md` to **score** retrieval is allowed. The banned thing is using
it to **write** a prompt. Scoring is not leakage.


### Slice 1 — the measurement, and the model is settled 2026-08-20

*Corpus: all 78 chunks of `B_train.py`, side B only. Queries: 17, in
`data/samples/quora_siamese/queries.json`. Four requests per run. Saved to
`artifacts/2026-08-20_21-58_embedder-choice.md`.*

| | `codestral-embed` | `mistral-embed` |
|---|---|---|
| recall@1 | 0.412 | 0.353 |
| **recall@5** | **0.941** (16/17) | 0.765 (13/17) |
| recall@10 | 0.941 | 0.882 |
| MRR | 0.613 | 0.529 |
| tokens for the same corpus | **14,979** | 19,143 |

**Decision: `codestral-embed` is the primary.** The rule was fixed before the run
— *win only on a recall@5 lead of at least 10 points* — and the lead is **17.6**.
`MIGRATION` already had it first, so no code changed; the order now rests on
evidence instead of on a description.

**Per-query direction, which is the more honest signal:** codestral is better on
**8** queries, worse on **3**, tied on **6**. With 17 queries, those 3 wins *are*
the entire 17.6 points — so read the direction, not the headline.


#### The second question mattered more, and it passed

The run was designed to answer two things. **Does retrieval work at all on this
data?** At 94% recall@5, yes — far above the ~50% line below which the model
would not have been the problem. **Chunking and the query design are sound**, so
slice 2 can proceed without reopening them.


#### The queries must never contain the identifier they look for

`gradients are clipped at a global norm of 1.0`, never `CLIP_NORM`. A query
holding the identifier measures string matching, not retrieval, and it would have
scored ~100% for both models while proving nothing. Same family as *never write
the prompt from the answer key*.

**Two ground-truth entries were corrected mid-run, and the distinction matters.**
`D8` and `D9` had been transcribed from `EXPECTED.md` incompletely — it cites
`255, 1332-1338` and `1146-1147`, and only one line of each had been written
down. **Fixing an incomplete transcription is legitimate; adding a target because
a model missed is not.** `D2` was left exactly as `EXPECTED.md` cites it, even
though widening it would have flattered the winner.


#### The one real miss is a design finding, not a weakness

`D2` — *"gradients are clipped at a global norm of 1.0"* — ranked **41** on
codestral, and 3 on mistral. What codestral returned instead:

```
1.  class Trainer · def _backprop_with_scaler · lines 1069-1091   <- clip_grad_norm_ is CALLED here
2.  class QuoraSiameseClassifier · def _encode
wanted: the config block holding CLIP_NORM = 1.5
```

**It retrieved the implementation rather than the constant.** For *"where are
gradients clipped?"* that is the better answer. For **our** task it is useless,
because the divergence lives in the value `1.5`.

> **A code embedder answers "where does this happen", not "what is this set to".
> Configuration constants are a distinct retrieval need.**

This is measured support for a rule already in this file — *route by question
type; a training question always fetches the training loop, the optimizer and the
loss, whatever their scores.* Config blocks need the same. **It belongs to slice
7**, and `D2` is the test case for it.

Note also that the two models' misses barely overlap — codestral fails `D2`,
mistral fails `D3`, `D4`, `D7`, `D9`. The same disjoint-blind-spot shape found in
the generators. Do not over-read one query, but it is a reason to keep the second
model reachable rather than deleting it.


#### The 20-minute ingest is really about 8, and that weakens the routing case

Measured on real chunks: **192 tokens per chunk**, not the 500 assumed
everywhere in this file.

$$
\frac{2{,}000 \times 192}{50{,}000} \approx 7.7\ \text{minutes}
$$

So the operational cost that
[open question 2](../../llm/embedder-chain.md#three-open-questions--answer-them-at-step-1-with-measurements)
exists to avoid is **less than half** what was assumed. Condition 1 of the
routing rule is now met; **condition 2 looks much weaker than it did**. Still not
decided — it needs a real repository, which is slice 2. Recorded so the decision
at slice 8 starts from the measured number, not the guessed one.

**And `codestral-embed` uses 22% fewer tokens on the same text** (14,979 against
19,143), because its tokenizer is built for code. Part of its 400× rate
disadvantage is bought back on every call.


#### What slice 1 shipped

| Module | Holds |
|---|---|
| `labpilot/_text.py` | `truncate`, `ERROR_BODY_CHARS`, moved up out of `llm/` |
| `embed/errors.py` | `EmbeddingError` — message only, until a retry policy branches on it |
| `embed/contracts.py` | `Vector`, `EmbeddingBatch`, validated at construction |
| `embed/defaults.py` | `DEFAULT_TIMEOUT`, `MAX_BATCH_SIZE`, `TIGHTEST_TOKENS_PER_MINUTE` |
| `embed/mistral.py` | `MistralEmbedder` — one call, one request |
| `embed/registry.py` | `CODESTRAL_EMBED`, `MISTRAL_EMBED`, `MIGRATION` |
| `data/samples/quora_siamese/queries.json` | 17 graded queries, the retrieval fixture |

**290 unit/api/integration tests, 21 smoke, ruff clean.**

Three decisions inside it that are worth not re-deriving:

- **`embed()` is exactly one HTTP request.** More than `MAX_BATCH_SIZE` texts is a
  `ValueError`. The loop over 2,000 chunks belongs to ingest orchestration in
  slice 4, with the streaming rule already written down.
- **`MAX_BATCH_SIZE = 96` is derived**, `floor(50,000 / 510)`, and
  `test_a_full_batch_of_capped_chunks_fits_the_tightest_token_budget` now enforces
  the derivation across two packages. Raising the chunk cap breaks the build
  instead of breaking a quota silently.
- **We normalize; the provider is not trusted to.** Measured:
  `mistral-embed` returns 1.000015, `codestral-embed` returns 0.993116.


### Slice 1b — more embedders, and why it moved ahead of slice 2

*Decided 2026-08-20 at the user's request. Step 1 is now **nine** slices: 1, 1b,
then 2 through 8.*

`MIGRATION` holds two models, both on one platform. Chain 2 lists five. Slice 1b
adds the next ones and measures them **on `queries.json`, which already exists**
— so it needs no repository and no new fixture.

| Must do | Why |
|---|---|
| add `gemini-embedding-001` | the real **cross-platform** backup — today one Mistral outage stops all ingest |
| add one open-weights model (`@cf/baai/bge-*`) | the only option that can also run locally, and a third independent quota |
| **measure each on `queries.json`** | recall@5 and recall@1 against codestral's 0.941 / 0.412 |
| **record each one's real rate limit** | read from a live 429 or the provider's own page, never from a blog |
| extract `base.py` | the second wire shape finally exists, so the seam can be observed instead of guessed |

**Why it moved ahead of slice 2.** Two reasons, and both are about not building on
an unknown:

1. The routing rule below may name Google. **We have never called Google's
   embedder.** This project's rule is that an unproven provider is not a
   provider — Cerebras was "verified" for three days and had never returned a
   token.
2. `base.py` is cheaper to extract now than after four more modules import
   `MistralEmbedder` directly.

**What slice 1b cannot answer, and must not pretend to:** the routing threshold.
That needs a corpus large enough to hurt, which arrives in slice 2. 1b measures
*quality and rate*; slice 2 measures *pain*.

**Two traps waiting in it.** `gemini-embedding-001` takes at most **2,048 input
tokens** — fine against our 510-token cap, but it removes the option of ever
raising that cap. And Google returns **one aggregated vector** when several
inputs are passed directly; each input must be wrapped in its own `Content`
object. That was verified live on 2026-08-11 and is exactly the kind of silent
mistake `test_vectors_follow_input_order...` exists to catch.


### Hybrid search — decided 2026-08-20, built in slice 5

**The measured case for it is `D2`.** The query was *"gradients are clipped at a
global norm of 1.0"*; the answer is `CLIP_NORM = 1.5`. Codestral ranked it
**41st**, and returned the line that *calls* `clip_grad_norm_` instead.

> **Vectors are good at meaning. Keywords are good at names. Code is mostly
> names.**

A keyword search matches `clip` and `norm` immediately, because they are inside
the identifier. A vector search does not, because an identifier is not prose.

So slice 5 builds **both**: cosine over the vector column, and Postgres
full-text search over the chunk text, fused into one ranking. It costs **no
model, no quota and no new provider** — only a second index.

Two things to settle when it is built, by measurement and not by argument:

- **How the two rankings fuse.** Reciprocal rank fusion is the usual answer and
  needs no score calibration, which matters because a cosine and a BM25 score are
  not on the same scale and must never be added directly.
- **Whether it actually helps.** `D2` is the test case, and `queries.json` gives
  the before-and-after number for free. If recall@5 does not move, do not keep it.

**This is the first retrieval idea in the project that came from a measurement
rather than from a design document.** Record which future ones do too.


### Slice 1b — DONE 2026-08-20, and Google is blocked

**Shipped:** `base.py` extracted, `CloudflareEmbedder` added and measured,
`MIGRATION` reordered on a structural reason, and one real bug found by a guard
written the same hour.

**Superseded — Google and Cohere were added later the same day. The current
numbers are in
[the second pass](../../step1/embedders-measured.md#slice-1b-second-pass--five-embedders-and-cohere-is-the-surprise).**

| | codestral-embed | **@cf/bge-base-en-v1.5** | mistral-embed |
|---|---|---|---|
| dim | 1536 | **768** | 1024 |
| recall@1 | **0.412** | 0.294 | 0.353 |
| **recall@5** | **0.941** | **0.824** | 0.765 |
| recall@10 | 0.941 | 0.882 | 0.882 |
| MRR | **0.613** | 0.523 | 0.529 |
| tokens for the same corpus | **14,979** | 39,936 | 19,143 |
| platform | Mistral | **Cloudflare** | Mistral |

**`codestral-embed` still wins, by more than before.** Slice 1's decision stands
and is now tested against a third model on an independent platform.


#### Google could not be added, and the reason is bigger than slice 1b

```
POST .../gemini-embedding-001:batchEmbedContents  -> 400 FAILED_PRECONDITION
POST .../gemini-3.5-flash-lite:generateContent    -> 400 FAILED_PRECONDITION
     "User location is not supported for the API use."
```

**Generation fails too, so this is not an embedding limitation.** By this file's
own table a `400 FAILED_PRECONDITION` is a **per-request check on the
connection's country**, distinct from the `403 PERMISSION_DENIED` that means the
account is flagged. Google answered live on 2026-08-17, three days earlier.

**Six generator tiers and the whole Google embedding option are unreachable from
here right now.** The weekly smoke run will fail on every Google tier. The
likeliest cause is the one this file already warns about: *"do not use this
account through a VPN or a location-switcher extension."*

**Nothing was written for Google**, deliberately. Code against a payload we could
not execute would be a guess, and *"an unproven provider is not a provider"* is
the rule that Cerebras taught. When the location is fixed, one command finishes
it — the probe script is in the session scratchpad.

> **RESOLVED 2026-08-27, and the diagnosis above was half wrong.** Google
> answers **200** again — generation and embedding both. The refusal was never
> about the account and never about the code, so that part held. But it was
> also **not about the ISP**: the exit today is the *same* `dataforest GmbH`
> that was refused on 2026-08-20. What changed was the tunnel mode and the exit
> IP. **A `400 FAILED_PRECONDITION` is per-IP, and an ISP owns many IPs** — so
> "this ISP is blocked" is a guess dressed as a measurement. The standing fix
> is [the network precondition](../../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work):
> probe the endpoint before every LLM session, and never conclude from the ISP
> name.


#### The guard found a real bug on its first run

`max_input_tokens` was added so a model that truncates silently would refuse
loudly instead. It fired immediately:

```
BGE Base EN v1.5: 3 text(s) exceed the 512 token input limit
  and would be silently truncated: [(28, 525), (53, 523), (54, 526)]
```

> **`MAX_CHUNK_TOKENS = 510` is enforced on `chunk.text`. What actually gets
> embedded is `chunk.embed_text` — text *plus header*.** Headers cost 10–31
> tokens (mean 21.6), so 3 of 78 chunks cross the cap.

**This is not only an embedding problem.** The 510 number exists because
[Cohere auto-splits longer documents](../../llm/reranker-chain.md#chain-3--reranker-true-fallback), which
silently multiplies the billed document count. The rerank budget arithmetic in
this file assumes documents stay under 510. **For 4% of chunks it is already
wrong**, and nothing would ever have reported it.

**Fix belongs in slice 3**, where the chunker is open anyway: the cap must be
applied to what is *sent*, not to what is *stored*. Doing it now would move chunk
boundaries and invalidate slice 1's baseline for no gain, because the guard has
already turned the failure from silent into loud.

> **Enforce a limit on the string you actually send.** A cap on an intermediate
> value is a cap on nothing.


#### The migration order changed, for a structural reason and not a score

`MIGRATION` is now **codestral → BGE → mistral-embed**.

BGE's 0.824 against mistral's 0.765 is **one query out of seventeen** — noise,
and explicitly *not* the reason. The reason is that `codestral-embed` and
`mistral-embed` share one API key: **a Mistral outage takes both**, and a
migration list whose top two die together is not a migration list.

`test_no_single_platform_can_empty_the_migration` now pins it, mirroring
`test_no_single_pool_can_kill_the_whole_chain` in the LLM layer.

**BGE is ranked second while being unusable today** — its 512-token limit is
below our own chunk sizes. That is the same pattern the generator chain already
uses for Gemma and Groq: *order by capability, let the limit fields handle
reachability.* It costs nothing, because `_check_texts` refuses before any HTTP
call, and it starts working by itself once slice 3 fixes the header bug.


#### `base.py` was extracted only once the second implementation existed

`HTTPEmbedder` holds the template — validate, POST, status, JSON, parse, count,
width, normalize, build. Subclasses supply five methods. The seam was **observed,
not guessed**, exactly as `llm/base.py` was.

The three genuine differences it exposed, none of which could have been predicted:

| | Mistral | Cloudflare |
|---|---|---|
| ordering | each item carries **`index`**, so sort by it | **no index** — position is the only signal |
| integrity check | count of `data` | **`shape: [n, 768]`**, cross-checked against `len(data)` |
| envelope | HTTP status only | **`success: false` inside a 200** |
| unknown fields | **422 `extra_forbidden`** | **silently ignored, 200** |

That last row is worth keeping. **Mistral refuses a typo; Cloudflare accepts it
and changes nothing.** Prefer the provider that refuses, and never assume a
rejected field on one host will be rejected on another.

`_raw_vectors` is where all four differences live, which is the test of whether
a seam is in the right place.


#### Two numbers worth remembering

**BGE's tokenizer is 2.7× less efficient on our corpus** — 39,936 tokens against
codestral's 14,979 for the identical text. A general-purpose tokenizer splits
code badly. This matters for any per-token budget, and it is invisible unless you
log the provider's own count.

**Cloudflare pooling is `mean`**, reported in its own response. That is the
`e = sum(m_i h_i) / sum(m_i)` from the slice 1 lesson, confirmed live rather than
assumed.


#### Review pass — what was added, and what was refused

Added: `test_every_embedder.py`, which parametrizes the shared contract over
`MIGRATION`, so a fourth embedder gets coverage automatically — the same pattern
that fixed five untested models in the LLM smoke suite.

**Refused: an `api/` test.** `services.py` still never touches the embedder, so a
test there would exercise no code. That changes at slice 7.

**Refused: a `test_base.py`.** The template is already exercised through two
concrete providers. A test of an abstract class in isolation would raise a number
and prove nothing.

**All 9 new invariants were mutation-tested and all 9 were caught** — including
the two that matter most, *"Cloudflare vectors are matched by position"* and
*"a text over the input limit costs no request"*.


### Slice 1b, second pass — five embedders, and Cohere is the surprise

*Google and Cohere were added at the user's request after the three-way pass
above. **The tables in that section are superseded by this one.***

**290 unit · 49 api · 7 integration · 24 smoke · ruff clean. All 14 new
invariants survived mutation testing.**

| | codestral | cohere v4 | bge-base | mistral | **gemini-embedding-001** |
|---|---|---|---|---|---|
| dim | 1536 | 1536 | 768 | 1024 | **3072** |
| recall@1 | 0.412 | **0.529** | 0.294 | 0.353 | **0.529** |
| **recall@5** | 0.941 | 0.882 | 0.824 | 0.765 | **1.000** |
| **recall@10** | 0.941 | **1.000** | 0.882 | 0.882 | **1.000** |
| **MRR** | 0.613 | **0.723** | 0.523 | 0.529 | 0.690 |
| tokens, same corpus | 14,979 | **13,412** | 39,936 | 19,143 | **not reported** |
| platform | Mistral | Cohere | Cloudflare | Mistral | **Google ✅** |

**The Google column was scored a week later, on 2026-08-27**, once the exit IP
stopped being refused — saved as `artifacts/2026-08-27_22-23_google-embedder-scored.md`.
`codestral-embed` was re-run in the same pass as a **control** and reproduced
its 2026-08-20 numbers exactly (0.412 / 0.941 / 0.941 / MRR 0.613), so the two
columns are comparable and the harness is not the variable.


#### Cohere is the best ranker, and it stays last anyway

This file already said *"Cohere is last on purpose, not because it is weak …
on quality it would rank higher."* **That was an assertion. It is now measured.**

`embed-v4.0` wins recall@1 (+11.7 points over codestral), wins MRR (+11.0), and
is the only model with **perfect recall@10** — every target inside the top ten,
never worse than 7th on any query. It is also the most token-efficient on our
corpus.

**And it still sits last in `MIGRATION`**, unchanged, because the reason was
never quality: its 1,000 calls/month are **one bucket shared by chat, embed and
rerank**, and Cohere is the reranker primary. A corpus embedded there keeps
spending the rerank budget on every query, forever. The ceiling is now confirmed
by the provider's own header, `x-endpoint-monthly-call-limit: 1000`.

> **A model can be the best one and still be the wrong one.** Rank by the
> resource that runs out, not only by the score.

**Which metric should have decided this?** Under the planned pipeline —
retrieve 50, rerank to 10 — **recall@10 matters more than recall@5**, because
reranking fixes ordering but cannot recover a chunk retrieval never returned.
On that measure Cohere is perfect and codestral is not. Slice 6 must re-read
this table once a reranker exists; the current order rests on recall@5, which
may be the wrong headline.


#### Google was scored on 2026-08-27, and it leads on recall

**`gemini-embedding-001` is the only model that put every target in the top 5.**
recall@5 **1.000** against codestral's 0.941 and Cohere's 0.882; recall@10 also
1.000, tying Cohere. Cohere keeps MRR (0.723 against 0.690), so Google ranks
*more* targets highly while Cohere ranks the top one slightly better.

**The result that matters most is `D2`, because it was our worst known miss.**
The query is *"gradients are clipped at a global norm of 1.0"* and the answer is
the constant `CLIP_NORM = 1.5`:

```
codestral-embed   rank 41    returned the line that CALLS clip_grad_norm_
gemini-embedding  rank  3    returned the config block
```

This file used `D2` as the measured argument for building hybrid keyword search
in slice 5 — *"vectors are good at meaning, keywords are good at names"*. **A
better embedder just weakened part of that argument.** Hybrid search is still
worth building and still cheap, but slice 5 must re-check whether it moves
recall@5 **on top of Google**, not on top of codestral. If it does not, do not
keep it.

> **A weakness you designed a feature around may belong to the model, not to the
> method.** Re-run the motivating case after any model change, or you ship a fix
> for a problem that no longer exists.

**Two costs Google carries that no other candidate does:**

1. **It cannot be indexed as a plain `vector`.** 3072 dimensions is above
   pgvector's 2000-dimension index ceiling, measured on the real Supabase
   project. It needs an **expression index on `(v::halfvec(3072))`**, or
   `outputDimensionality: 1536` — and that second option is a *different vector*,
   so its recall would have to be re-scored. **This is a slice 4 decision.**
2. **It reports no usage.** `batchEmbedContents` returns no usage block, so the
   token cost of an ingest cannot be read from the response — only estimated.
   Every other provider tells us.


#### The query/document asymmetry became real, and it may explain Cohere's lead

Cohere's v2 embed **requires** `input_type`, so the distinction this file has
described since 2026-08-13 could no longer be deferred. `embed()` now takes
`task: Task = "document"`, and each provider translates it:

| Provider | Wire form |
|---|---|
| Cohere | `input_type: search_document` / `search_query` |
| Google | `taskType: RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` |
| Mistral, Cloudflare | no such field — the argument is ignored |

**The only provider that has the asymmetry has the best ranking quality.** That
is one data point, not proof — but it is the first evidence in this project that
query–document asymmetry is worth paying for, and it is a reason to use Google's
`taskType` the moment Google is reachable.

`task` was deliberately **not** added during the first pass, when Google was the
only candidate consumer and Google could not be called. A parameter with no
working consumer is dead code; a parameter two providers translate is an
interface.


#### Google shipped unverified, on purpose — and it was proven right 2026-08-27

> **The quarantine is lifted.** `pytest tests/smoke/test_embedders.py --run-smoke`
> now reports **`XPASS` for `gemini-embedding-001`** — the exact signal point 2
> below was built to send, arriving seven days later. `dim = 3072` is
> **observed**, so the documented number was correct and `_validated` never had
> to fire. The remaining action is to **delete the `xfail` marker**, or a real
> future failure will be filed as an expected one. The two fields still
> unmeasured are unchanged: whether `batchEmbedContents` reports usage, and the
> real batch ceiling.
>
> **What this vindicates is the *shape* of the gamble, not the gamble.** Shipping
> unproven code was still against the rule. It was survivable only because every
> wire detail was pinned by tests and the one unobservable number would have
> raised loudly rather than storing a wrong-width vector. **Ship an unproven
> provider only when its first real call must either work or crash — never when
> it can quietly half-work.**

`GoogleEmbedder` is written from Google's documentation and **has never returned
a vector**. `gemini-3.6-flash`, `gemini-3.5-flash-lite` and
`gemini-embedding-001` all answer `400 FAILED_PRECONDITION — "User location is
not supported"` from this connection, re-tested on request.

This breaks the rule *an unproven provider is not a provider*, and it was shipped
anyway at the user's explicit instruction. Three things make that safe rather
than reckless:

1. **`dim=3072` is documented, never observed.** If it is wrong, `_validated`
   raises loudly on the first real call instead of storing a wrong-width vector.
2. **The smoke test marks it `xfail(strict=False)`**, the same treatment as
   GLM-5.2. The day the location is fixed it reports **XPASS**, which is the
   signal that would otherwise never arrive.
3. **Every wire detail is pinned by unit tests** — the key goes in
   `x-goog-api-key` and never in `Authorization`, each text gets **its own
   request object** (one request with several inputs returns a single aggregated
   vector), and the task maps to `RETRIEVAL_QUERY` / `RETRIEVAL_DOCUMENT`. All
   three were mutation-tested.

**Unverified fields to re-check the moment Google answers:** ~~the real
dimension~~ (**3072, confirmed 2026-08-27**), whether `batchEmbedContents`
reports usage, and the real batch ceiling.


#### The registry test earned itself within the hour

`COHERE_API_KEY` was documented in `.env.example` and **not mapped in
`smoke.yaml`**. `test_every_embedder_env_var_is_mapped_in_the_smoke_workflow`
failed the moment Cohere joined `MIGRATION` — the identical failure shape as the
2026-08-11 `OPENROUTE_API_KEY` typo, caught this time before it ever ran.

A second detail worth remembering: the anchor edit failed twice because
`smoke.yaml` **ended without a trailing newline**, so the last mapping line had
no terminator. Text files that end mid-line break naive patching.


#### Mutation testing found a decision that lived only in a comment

Thirteen of fourteen mutations were caught. The survivor: pointing BGE at
`MISTRAL_API_KEY` did **not** break
`test_no_single_platform_can_empty_the_migration` — with five embedders across
four platforms, that invariant genuinely still holds.

The property actually claimed in `registry.py` was stronger, and untested:
*BGE sits second because it is the only early entry on a different platform.*

`test_the_two_best_embedders_do_not_share_a_platform` now pins it. **A migration
is not a fallback** — recovering means re-embedding the whole corpus by hand, so
if the top two die together that manual step is forced onto a model that is
unmeasured, blocked, or paid out of the reranker's own bucket.

> **The mutation did not reveal a broken test. It revealed a missing one.** A
> design decision that lives only in a comment is a decision nothing defends.


#### Provider differences, now four wire shapes deep

| | Mistral | Cloudflare | Cohere | Google |
|---|---|---|---|---|
| auth | Bearer | Bearer | Bearer | **`x-goog-api-key`** |
| batch field | `input` | `text` | `texts` | **one request object per text** |
| ordering | **`index`** | position | position | position |
| vectors at | `data[].embedding` | `result.data` | **`embeddings.float`** | `embeddings[].values` |
| usage at | `usage` | `result.usage` | `meta.billed_units` | **absent — 0** |
| integrity extra | — | **`shape`** | — | — |
| envelope failure | — | **`success:false` in a 200** | — | — |
| unknown field | **422** | **ignored** | — | — |

All eight rows live inside `_raw_vectors`, `_payload` and `_prompt_tokens`.
Nothing leaked into the shared template, which is the test of whether
`base.py` was cut in the right place.
