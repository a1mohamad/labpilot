# Chain 2: the embedders

[Docs home](../README.md)

### Chain 2 — Embedder (migration, not fallback)

**One model per corpus, pinned. Never mixed.** The list below is a *migration
order*, used when the primary is dead — not a per-request fallback.

| # | Model | Provider | Dim | Note |
|---|---|---|---|---|
| 1 | **`codestral-embed`** | Mistral | **1536** | The only **code-specific** embedder found. 50K TPM ≈ 20 min per 1M-token repo — fine, ingest is offline. **Verified live 2026-08-11.** |
| 2 | `mistral-embed` | Mistral | **1024** | **20M TPM** — same repo in ~3 seconds. Same platform, so swapping is easy. **Verified live 2026-08-11.** |
| **3** | **`gemini-embedding-2`** | **Google ×2 keys** | **3072** | **NEWER and ranked above 001 — version `2`, MTEB 69.9 vs 68.32, and 8,192 input tokens. Added 2026-09-11. UNMEASURED on our fixture** |
| 4 | `gemini-embedding-001` | Google ×2 keys | 3072 | The measured one: **perfect recall@5**, the only model to manage it. Max input **2,048 tokens** |
| 4 | `@cf/baai/bge-*` | Cloudflare | 384 / **768** / 1024 | Open weights — **also runs locally via ONNX**, the only true two-runtime option. `bge-base-en-v1.5` verified live at **768 dim**, 2026-08-11. |
| 5 | `embed-v4.0` | Cohere | — | **Deliberate last resort — see below.** 128K input context, strong model. |

**Why Cohere is last on purpose, not because it is weak.** *(Confirmed
2026-08-11.)* `embed-v4.0` is a good embedder with a 128K input window — on
quality it would rank higher. It sits last because of **quota shape**, not
capability:

Cohere's 1,000 calls/month is **one bucket shared by chat, embed and rerank**, and
Cohere is the reranker primary. Migrating a corpus to Cohere is not a one-off
cost — the corpus stays locked to that model, so **every future query embeds
through Cohere too**:

$$
20 \text{ questions/day} \times 30 = 600 \text{ query embeds/month}
$$

That would leave ~400 calls for reranking (~13/day) and quietly starve the job
Cohere exists to do. So it is kept as a **safety guard**: reachable if the four
above are all gone, never entered casually.

**And migrate back when the primary recovers.** A corpus stranded on Cohere keeps
spending the rerank bucket forever. Re-embedding it back to Mistral or Google is
a cheap background job and returns the quota. Same rule as any migration: the
model is a property of the corpus, so fixing it means re-embedding, not a setting
change.

**Dimension changes are schema changes.** `codestral-embed` is 1536 and
`mistral-embed` is 1024, so migrating between them alters the pgvector column
type (`vector(1536)` → `vector(1024)`), not just the rows.

**Store `embedding_model` and `dim` on every row.** Then a model mismatch is
*detected* instead of silently poisoning search.

**Two gotchas, verified 2026-08-11:**
- Google's batch call returns **one aggregated vector** when several inputs are
  passed directly. Each input must be wrapped in its own `Content` object.
- Mistral has **no reranker at all** — `GET /v1/models` returns zero matches.

#### Retry vs re-embed — the rule

Re-embedding is the answer to a *dead* provider, not a busy one:

| Failure | Response |
|---|---|
| 429 / timeout — **transient** | **Retry.** Quota resets; retrying is far cheaper than re-embedding |
| 403 / dead account — **permanent**, or retries exhausted | **Migrate:** re-embed the whole corpus with the next model |

**Never continue a half-finished corpus with a different model.** If ingest dies
at chunk 1,200 of 2,000, delete the 1,200 and redo all 2,000 — do not embed the
remaining 800 with the new model. Re-embedding is cheap (~1M tokens ≈ 2 cents,
or free); *mixing* is unrecoverable.

**Budget before starting.** Chunk count is known before the first call, so check
it against remaining quota and refuse to *start* rather than dying halfway. Same
idea as the pre-flight token validator for generation.

**The model is a property of the corpus, not a global setting.** Repo X on
Mistral and Repo Y on Google can coexist; each queries with its own model. When
the primary recovers it is used for **new** corpora automatically — old ones stay
put until deliberately re-embedded, which is optional and usually not worth it.

#### Three open questions — answer them at Step 1, with measurements

*Raised 2026-08-14 during slice 3. None can be answered now: slice 3 produces no
vectors. All three are recorded so Step 1 does not start by guessing.*

**1. Is `codestral-embed` actually better than `mistral-embed` on our data?**
Nobody has checked. Tier 1 was chosen because it is the only **code-specific**
embedder found, which is an argument from description, not from evidence. The
speed difference is enormous and comes entirely from free-tier rate limits, not
from hardware:

| Model | TPM | 1M-token repo | Dim |
|---|---|---|---|
| `codestral-embed` | 50,000 | **~20 min** | 1536 |
| `mistral-embed` | 20,000,000 | **~3 s** | 1024 |

**The test:** embed `data/samples/quora_siamese/` both ways, run the same fixed
query set, and compare which chunks return. If `codestral` does not win clearly,
**use `mistral-embed` everywhere** — one model, one dimension, and question 2
disappears with it.

**2. Should the embedder be chosen by corpus size?** *(User's proposal, and the
corrected form of it.)* Estimate the tokens of **both artifacts together**; above
~50,000, use the fast model.

- **The per-session part is essential, not cosmetic.** Choosing per *artifact*
  would let side A be embedded by one model and side B by another, and then the
  alignment matrix compares across models — the exact `cos(E_A(q), E_B(d))` =
  noise failure the migration rule exists to prevent. One decision, both sides.
- **The argument for it is Render, not impatience.** Ingest runs *in the same
  process as the API* on a 512MB free instance that spins down when idle, so a
  20-minute embed holds the serving process and can be interrupted. That is an
  operational risk, not a wait.
- **The argument against it** is that retrieval is hardest on large corpora,
  which is exactly where the rule would use the weaker model — and small corpora
  barely need retrieval at all.
- **It is not blocked by schema.** An earlier objection said the 1536/1024
  difference made this expensive; that was wrong. Coexistence of models — and
  therefore of dimensions — is *already* required by the paragraph above.

**Resolve question 1 first.** If `mistral-embed` wins, question 2 is moot.

**The condition that decides it — written 2026-08-20, before any number
exists, so it cannot be bent afterwards.** Routing by corpus size is real only
if **both** hold:

1. `codestral-embed` beats `mistral-embed` by **at least 10 points recall@5**
   *(slice 1)*, **and**
2. on a **real repository**, its ingest is slow enough to be an operational
   problem on Render, where ingest holds the same 512MB process the API is
   serving from *(slice 8)*.

Only 1 → use `codestral-embed` everywhere. Only 2 → use `mistral-embed`
everywhere. Both → the routing rule earns its place.

**The designed shape, recorded 2026-08-20 with the threshold left unknown.**
The user's position, and it is reasonable: on Render ingest **blocks the API
process**, so a long ingest is an operational problem and not merely a wait.

```
corpus size  ->  which embedder
  small       ->  codestral-embed   best recall: 0.941 recall@5
  large       ->  mistral-embed     400x the token rate, 0.765 recall@5
threshold: UNKNOWN - measured in slice 2, decided in slice 8
```

Three things must hold before it ships, and none is settled by argument:

1. **The threshold comes from slice 2's real repository.** Guessing it now
   would repeat the 20-minute estimate, which measurement already halved.
2. **Google must be proven and its rate limit measured first** — slice 1b. An
   unproven provider is not a provider.
3. **A corpus stays locked to whichever model embedded it.** So a "large"
   corpus can never later be compared against a "small" one. Know that before
   the rule exists, not after.

**A third option neither side has costed:** keep `codestral-embed` and move
ingest off the request process. That removes the trade entirely, and it is a
Step 3 change. Price it before accepting a recall loss.

**And it cannot be settled in slice 1, for a measurable reason:** the rule
exists to avoid a 20-minute ingest, and **no corpus that takes 20 minutes
exists yet**. The fixture is 96 chunks — about 3 seconds on either model. A
repository-sized corpus arrives in slice 2, so **the decision date is slice
8**. Slice 1 picks a default, not a policy.

#### The pgvector dimension ceiling — measured 2026-08-27, and it binds

*Run on the real Supabase free project (`LabPilot`), pgvector **0.8.2**. Not
read from docs — the docs describe pgvector in general, and what matters is the
version actually installed where we deploy.*

| what | 3072 dimensions |
|---|---|
| `create table (v vector(3072))` | ✅ **stores fine** — storage is not the limit |
| `hnsw` on `vector` | ❌ `54000: column cannot have more than 2000 dimensions` |
| `ivfflat` on `vector` | ❌ **same error** — so it is a pgvector-wide cap, not an hnsw quirk |
| `hnsw` on **`halfvec(3072)`** | ✅ **works** |
| **`hnsw` on the expression `(v::halfvec(3072))`** | ✅ **works — and this is the answer** |

**This is the constraint that actually decides the embedder, and no recall
number can overrule it.** `gemini-embedding-001` returns **3072** dims. Without
an index every query is a sequential scan over the whole corpus, which is fine
at 78 chunks and useless at 2,000. **A model that cannot be indexed is not a
candidate, however well it scores.**

Three ways out, and each has a price that must be **measured**, not assumed:

| option | keeps | costs |
|---|---|---|
| **expression index on `(v::halfvec(3072))`** | **full 32-bit storage** *and* a working index | half precision **inside the index only** |
| `halfvec(3072)` column | one index, simplest schema | 16-bit **everywhere**, including storage |
| **`outputDimensionality: 1536`** | plain `vector`, same width as codestral and cohere | a different vector; **recall must be re-scored**, and Google's docs say truncated vectors must be re-normalized |
| no index | exact search | O(N) per query — dies past a few thousand chunks |

#### The workaround was proven end to end - measured 2026-08-28

*Run in the Supabase SQL editor on the real `LabPilot` project, on **2,000 rows
of random `vector(3072)`**. Random vectors are the hardest case for approximate
search, because real embeddings cluster and random ones do not.*

| # | Question | Result |
|---|---|---|
| 2 | does the ceiling really bite? | **yes** - `54000: column cannot have more than 2000 dimensions for hnsw index` |
| 3 | does the expression index build? | **yes** |
| 4 | **does a query USE it?** | **yes** - `Index Scan using probe_hnsw on probe`, **64.7 ms** |
| 5 | what does the natural form do? | **`Seq Scan on probe`, 326.0 ms - no error, no warning** |
| 6 | what does half precision cost? | **nothing measurable - 10 of 10 overlap with exact full-precision search** |
| 7 | what does it cost to store? | **42 MB table + 16 MB index**, for 2,000 rows |

**So Google is storable, searchable and indexable. The gate is passed.** This
upgrades `gemini-embedding-001` from *"blocked by an unproven workaround"* to a
real candidate - the ranking question then belongs to slice 8.

**The trap is real, and it is exactly 5x today.** Rows 4 and 5 differ only in
how the query is written:

```sql
order by v::halfvec(3072) <=> $1::halfvec(3072)   -- Index Scan,  64.7 ms
order by v <=> $1                                 -- Seq Scan,   326.0 ms
```

$$
\frac{326.0}{64.7} \approx 5\times \quad \text{at 2,000 rows}
$$

**And 5x is the smallest the gap will ever be.** An index scan grows like
`log N`, a sequential scan like `N`, so at 20,000 chunks the same mistake costs
an order of magnitude. It produces **no error and no warning** - which is why
slice 4 must assert the plan, not the result.

> **Write the query the way the index was built, or the index is decoration.**
> The failure is silent, and correctness never changes - only speed. Nothing
> tells you except `EXPLAIN`.

**What row 6 does and does not prove.** It compares the top 10 through
`halfvec` against the top 10 at full `float32`, and they are identical. That
settles **precision loss**: halving the bits did not move a single result. It
does *not* settle HNSW's own graph recall at real scale, which is tuned with
`hnsw.ef_search` and is a separate slice 4 job.

**Storage is the one real cost, and it is 2x.** 3072 dims store at ~21 KB a row
once page and TOAST overhead is counted, against ~10 KB for a 1536-dim model:

$$
\frac{500 \text{ MB free tier}}{58 \text{ MB per 2,000-chunk corpus}} \approx 8
\text{ corpora}
$$

Enough for the project, and worth watching. A 1536-dim model roughly doubles
that headroom.

**The expression index is the one to build if Google is ever chosen.** An
**expression index** indexes the *result of a cast*, not the column: Postgres
computes `v::halfvec(3072)` per row and indexes that copy. So the stored vector
keeps full precision and only the search shortlist is approximate — which is
exactly the shape the pipeline already wants, because
[slice 6](../step1/plan.md#the-nine-slices) reranks the shortlist anyway. Two things it
demands, and forgetting either silently disables the index: the query must be
cast the same way (`v::halfvec(3072) <=> $1::halfvec(3072)`), and the operator
class must be `halfvec_cosine_ops`.

> **Check the index limit before the quality benchmark, not after.** We scored
> five embedders on recall before asking whether the winner could be stored. The
> cheap question was the deciding one.

**Every other embedder is unaffected** — codestral 1536, cohere 1536, mistral
1024, bge 768 all sit under 2000 and index as plain `vector`.

**3. How are two dimensions stored at once?** **Partly dissolved 2026-08-20:**
`codestral-embed` accepts `output_dimension`, so it can return **1024** — the
same width as `mistral-embed`, and therefore one pgvector column type for both.
The *storage* problem shrinks; the **mixing** problem does not move at all, so
`embedding_model` on every row is still required. See
[slice 1's measurements](../step1/embedders-measured.md#slice-1--what-the-embeddings-endpoint-really-does-measured-2026-08-20).

This is owed by the existing
coexistence rule regardless of question 2. A pgvector index needs a fixed
dimension per column, so the options are one table per dimension, or one table
with `vector_1536` and `vector_1024` columns. Decide when the first second-model
corpus actually exists.

**What slice 3 owes all three: nothing but two fields.** `Chunk` carries
`embedding_model: str | None = None` and `dim: int | None = None`, both left
`None`. The chunker must never fill them — it does not embed, and a field it set
would be a claim about work it did not do.
