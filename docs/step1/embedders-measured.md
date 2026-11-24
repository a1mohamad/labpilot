# Step 1, slices 1 and 1b: the embedders measured

[Docs home](../README.md)

### Slice 1 — what the embeddings endpoint really does, measured 2026-08-20

*Mistral's docs site is JavaScript-rendered, so the endpoint was probed directly: four requests.* `input` takes a list (items return `{embedding, index, object}`); dimensions
`mistral-embed` **1024**, `codestral-embed` **1536**; `output_dimension` **works on codestral** (asked 512, got 512); **no `input_type` / query-vs-document flag** (unknown fields are
**rejected, `422 extra_forbidden`**); rate headers on a 200: `x-ratelimit-limit-req-minute: 60`.

#### The two models disagree about normalization — so we must normalize

`mistral-embed` norm 1.000015 (unit length); `codestral-embed` **0.993116** (NOT unit); codestral @ 512 → 0.920005. Trusting the provider would have been silently wrong (no error,
every cosine just a little off), so every vector leaving `labpilot/embed/` is normalized **by us**, once, and `cos(u,v)` is a plain dot product downstream. **Never assume a provider
returns unit vectors; measure the norm.**

#### Mistral rejects unknown fields, which is the good failure

`input_type: "query"` → 422 `extra_forbidden`: there is no query/document asymmetry parameter here (unlike Voyage `input_type`, Cohere `search_query`/`search_document`, E5/BGE text
prefix), and a payload typo **fails loudly** (OpenRouter silently drops unknown fields). **Prefer the provider that refuses.**

#### `output_dimension` is real, and the model is Matryoshka-trained

Same text at 1536 → norm 0.993116, at 512 → 0.920005; equal information per dimension would leave `sqrt(1/3) = 0.577` of the length, instead `(0.920005/0.993116)² = 0.86`: **the
first 512 dimensions hold ~86% of the energy, not 33%** — the signature of **Matryoshka Representation Learning** (early dimensions carry meaning, later ones refine). So
truncating is a **gentle** trade; **86% of the energy is not 86% of retrieval quality** (only recall@k measures that); and it is a **recorded lever, not a slice 1 decision**
(codestral can be asked for 1024, the width of `mistral-embed`). **Same dimension is not the same space**: it solves *storage*, never *mixing* (every row still carries
`embedding_model`), and does **not** help speed (the 50,000 TPM counts *input*).

#### The design decisions this settled

Embedders do **not** inherit `HTTPProvider` (a *completion* template: `tier`, `context_window`, `max_output_tokens`, `finish_reason` would be four fields of fiction) · no `base.py`
yet (one implementation; earned when Google landed) · reuse **`truncate` only**, promoted to `labpilot/_text.py` (two packages read it, like `estimate_tokens` → `labpilot/tokens.py`)
· error type **`EmbeddingError`** (one vocabulary per layer; `error_from_response` returns `LLMError` and stays in `llm/`) · the registry is **`MIGRATION`**, never `CHAIN` (a migration order is not a fallback loop; the name invites the loop that
must never exist) · **sort results by `index`** (a silent shift puts every vector on the wrong chunk).

#### The failure branches, all real

`ValueError` for a caller's bug (empty list, blank string); `EmbeddingError` for the provider (missing `MISTRAL_API_KEY`, `RequestException`, non-200, non-JSON, `len(data) !=
len(texts)` — "a length shift is silent and total", dimension ≠ the declared `dim` — the mismatch detector Chain 2 asks for, a zero vector — cannot be normalized, and it is finding
#18 in our own fixture).

### The slice 1 measurement, and its decision rule written first

**Two questions, the second more important:** which model, and **does retrieval work at all on this data?** (recall@5 under ~50% for *both* would mean chunking or the query text is the
problem). Ground truth: ~15-17 pairs *(query text, the line in `B_train.py` that answers it)* in `data/samples/quora_siamese/queries.json`; queries are `A_paper.md` claims (the
B-only findings get a short checklist phrase); stored as a **line number** resolved to whichever chunk contains it, so the file survives any change to chunk boundaries.
`recall@k = (1/|Q|) Σ 1[r_q ≤ k]`, `MRR = (1/|Q|) Σ 1/r_q`. **The decision rule, fixed before any number:** *`codestral-embed` wins only if its recall@5 is at least 10 points
higher; otherwise use `mistral-embed` (1024 dims, 400× the token rate, one model everywhere).* Using `EXPECTED.md` to **score** retrieval is allowed; using it to **write** a prompt is
banned.

### Slice 1 — the measurement, and the model is settled 2026-08-20

*All 78 chunks of `B_train.py`, side B, 17 queries, four requests per run; saved to `artifacts/2026-08-20_21-58_embedder-choice.md`.*

| | `codestral-embed` | `mistral-embed` |
|---|---|---|
| recall@1 | 0.412 | 0.353 |
| **recall@5** | **0.941** (16/17) | 0.765 (13/17) |
| recall@10 | 0.941 | 0.882 |
| MRR | 0.613 | 0.529 |
| tokens for the same corpus | **14,979** | 19,143 |

**Decision: `codestral-embed` is the primary** (lead **17.6** points against the 10 required; `MIGRATION` already had it first, so no code changed). Per query codestral is better on
**8**, worse on **3**, tied on **6** — with 17 queries those 3 wins *are* the whole 17.6 points, so read the direction, not the headline. **The second question passed:** at 94%
recall@5, chunking and query design are sound. **Queries must never contain the identifier they look for** (`gradients are clipped at a global norm of 1.0`, never `CLIP_NORM`; it
would have scored ~100% for both). **Two ground-truth entries were corrected mid-run, and the distinction matters:** `D8` and `D9` had been transcribed incompletely (`EXPECTED.md`
cites `255, 1332-1338` and `1146-1147`); **fixing an incomplete transcription is legitimate, adding a target because a model missed is not** (`D2` was left exactly as cited
even though widening it would have flattered the winner).

#### The one real miss is a design finding, not a weakness

`D2` ("gradients are clipped at a global norm of 1.0") ranked **41** on codestral (3 on mistral): codestral returned `class Trainer · def _backprop_with_scaler · lines 1069-1091`
(where `clip_grad_norm_` is CALLED) and `class QuoraSiameseClassifier · def _encode`, not the config block with `CLIP_NORM = 1.5`. **It retrieved the implementation rather than the
constant**: better for "where are gradients clipped?", useless for ours, because the divergence lives in the value `1.5`.

> **A code embedder answers "where does this happen", not "what is this set to". Configuration constants are a distinct retrieval need.**

Measured support for *route by question type* (a training question always fetches the training loop, optimizer and loss; config blocks need the same); `D2` is the test case.
The two models' misses barely overlap (codestral fails `D2`; mistral fails `D3`, `D4`, `D7`, `D9`): the disjoint-blind-spot shape of the generators, a reason to keep the second model
reachable.

#### The 20-minute ingest is really about 8, and that weakens the routing case

Measured **192 tokens per chunk** on real chunks, not 500: `2,000 × 192 / 50,000 ≈ 7.7` minutes, less than half the assumed cost; condition 1 of the routing rule met, condition 2
much weaker, undecided until a real repository (slice 2). *(Section 5 of slice 7 later measured 341.6 tokens per chunk over a whole repository; section 9 measured codestral at ~3.3
minutes.)* `codestral-embed` also uses **22% fewer tokens** on the same text (14,979 vs 19,143; its tokenizer is built for code).

#### What slice 1 shipped

`labpilot/_text.py` (`truncate`, `ERROR_BODY_CHARS`) · `embed/errors.py` (`EmbeddingError`, message only until a retry policy branches on it) · `embed/contracts.py` (`Vector`,
`EmbeddingBatch`) · `embed/defaults.py` (`DEFAULT_TIMEOUT`, `MAX_BATCH_SIZE`, `TIGHTEST_TOKENS_PER_MINUTE`) · `embed/mistral.py` (`MistralEmbedder`, one call = one request) ·
`embed/registry.py` (`CODESTRAL_EMBED`, `MISTRAL_EMBED`, `MIGRATION`) · `queries.json`. 290 unit/api/integration + 21 smoke, ruff clean. Decisions not to re-derive: **`embed()` is
exactly one HTTP request** (more than `MAX_BATCH_SIZE` is `ValueError`; the loop over 2,000 chunks is ingest orchestration, slice 4); **`MAX_BATCH_SIZE = 96` is derived**,
`floor(50,000 / 510)`, and `test_a_full_batch_of_capped_chunks_fits_the_tightest_token_budget` enforces it across two packages (raising the chunk cap breaks the build, not a quota);
**we normalize; the provider is not trusted to.**

### Slice 1b — more embedders, and why it moved ahead of slice 2

*Decided 2026-08-20 at the user's request: Step 1 became **nine** slices (1, 1b, 2-8).* `MIGRATION` held two models on one platform; 1b adds the next ones and measures them on the
existing `queries.json` (no repository needed): `gemini-embedding-001` (the real **cross-platform** backup, today one Mistral outage stops all ingest), one open-weights model
(`@cf/baai/bge-*`, the only one that could also run locally, a third independent quota), measured recall@5/@1 against 0.941/0.412, each one's real rate limit **from a live 429 or the
provider's own page, never from a blog**, and `base.py` extracted (the second wire shape finally exists). It moved ahead of slice 2 because the routing rule may name Google and **we
had never called Google's embedder** (an unproven provider is not a provider; Cerebras was "verified" for three days and never returned a token), and because `base.py` is cheaper
to extract before four more modules import `MistralEmbedder`. It cannot answer the routing threshold (needs a corpus large enough to hurt, slice 2): 1b measures *quality and rate*,
slice 2 measures *pain*. **Two traps:** `gemini-embedding-001` takes at most **2,048 input tokens** (fine against 510, but it removes the option of raising that cap) and Google
returns **one aggregated vector** when several inputs are passed directly — wrap each input in its own `Content` object (verified live 2026-08-11; the kind of silent mistake
`test_vectors_follow_input_order...` exists to catch).

### Hybrid search — decided 2026-08-20, built in slice 5

**The measured case for it is `D2`** (codestral rank 41, returning the line that *calls* `clip_grad_norm_`): **vectors are good at meaning, keywords are good at names, and code is
mostly names** (a keyword search matches `clip` and `norm` inside the identifier; a vector search does not). Slice 5 builds both — cosine over the vector column plus Postgres
full-text over the chunk text, fused — at **no model, quota or new provider** cost, only a second index. To settle *by measurement*: how the two rankings fuse (reciprocal rank fusion
needs no score calibration; a cosine and a BM25 score must never be added directly) and whether it helps at all (`D2` is the test; if recall@5 does not move, do not keep it).
**The first retrieval idea in the project that came from a measurement rather than a design document.** *(Slice 5 then measured it, slice 8 overturned its decision: always on.)*

### Slice 1b — DONE 2026-08-20, and Google is blocked

Shipped: `base.py` extracted, `CloudflareEmbedder` added and measured, `MIGRATION` reordered on a structural reason, and one real bug found by a guard written the same hour.
*(Superseded the same day by the second pass below; the tables here are kept for the three-way result.)*

| | codestral-embed | **@cf/bge-base-en-v1.5** | mistral-embed |
|---|---|---|---|
| dim | 1536 | **768** | 1024 |
| recall@1 | **0.412** | 0.294 | 0.353 |
| **recall@5** | **0.941** | **0.824** | 0.765 |
| recall@10 | 0.941 | 0.882 | 0.882 |
| MRR | **0.613** | 0.523 | 0.529 |
| tokens for the same corpus | **14,979** | 39,936 | 19,143 |
| platform | Mistral | **Cloudflare** | Mistral |

`codestral-embed` still wins, by more than before.

#### Google could not be added, and the reason is bigger than slice 1b

`batchEmbedContents` AND `gemini-3.5-flash-lite:generateContent` both answered `400 FAILED_PRECONDITION "User location is not supported for the API use."` — **generation fails too**, a
per-request check on the connection's country, distinct from the `403 PERMISSION_DENIED` that means the account is flagged (Google had answered live three days earlier). Six
generator tiers and the whole Google embedding option were unreachable; **nothing was written for Google** (code against a payload we cannot execute is a guess).

> **RESOLVED 2026-08-27, and the diagnosis was half wrong.** Google answers **200** again (generation and embedding). The refusal was never the account or the code, and **also not the
> ISP**: the exit was the *same* `dataforest GmbH` refused on 2026-08-20; what changed was the tunnel mode and the exit IP. **A `400 FAILED_PRECONDITION` is per-IP, and an ISP
> owns many IPs**, so "this ISP is blocked" is a guess dressed as a measurement. The standing fix is
> [the network precondition](../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work): probe the endpoint before every LLM session; never conclude from the ISP name.

#### The guard found a real bug on its first run

`max_input_tokens` (added so a truncating model refuses loudly) fired immediately: `BGE Base EN v1.5: 3 text(s) exceed the 512 token input limit and would be silently truncated:
[(28, 525), (53, 523), (54, 526)]`. **`MAX_CHUNK_TOKENS = 510` was enforced on `chunk.text`, but what is embedded is `chunk.embed_text` — text *plus header*** (headers 10-31 tokens,
mean 21.6; 3 of 78 chunks crossed). Not only an embedding problem: 510 exists because [Cohere auto-splits longer documents](../llm/reranker-chain.md#chain-3--reranker-true-fallback), silently multiplying billed
documents, so the rerank arithmetic was wrong for 4% of chunks with nothing reporting it. The fix belonged to slice 3 (done 2026-09-05, "the chunk cap fix"). **Enforce a limit on the
string you actually send; a cap on an intermediate value is a cap on nothing.**

#### The migration order changed, for a structural reason and not a score

`MIGRATION` became **codestral → BGE → mistral-embed**. BGE's 0.824 vs mistral's 0.765 is one query of seventeen — noise, explicitly *not* the reason; the reason is that
`codestral-embed` and `mistral-embed` share one API key, so **a Mistral outage takes both** and a migration list whose top two die together is not a migration list.
`test_no_single_platform_can_empty_the_migration` pins it (mirroring `test_no_single_pool_can_kill_the_whole_chain`). BGE is ranked second while unusable (its 512 limit was below our
chunk sizes): *order by capability, let the limit fields handle reachability* — `_check_texts` refuses before any HTTP call.

#### `base.py` was extracted only once the second implementation existed

`HTTPEmbedder` holds the template (validate, POST, status, JSON, parse, count, width, normalize, build); subclasses supply five methods; the seam was **observed, not guessed**. The
real differences, unpredictable beforehand: ordering (Mistral each item carries **`index`**; Cloudflare **no index**, position only) · integrity (count of `data` vs **`shape:
[n, 768]`** cross-checked against `len(data)`) · envelope (HTTP status only vs **`success: false` inside a 200**) · unknown fields (**422 `extra_forbidden`** vs **silently ignored,
200**). **Mistral refuses a typo; Cloudflare accepts it and changes nothing** — never assume a rejected field on one host is rejected on another. `_raw_vectors` holds all four
differences, which is the test of whether a seam is in the right place.

**Two numbers worth remembering:** BGE's tokenizer is **2.7× less efficient** on our corpus (39,936 vs 14,979 tokens for identical text), invisible unless you log the provider's own
count; Cloudflare pooling is `mean`, reported in its own response (`e = Σ m_i h_i / Σ m_i`, confirmed live). **Review pass:** added `test_every_embedder.py` (the shared contract
parametrized over `MIGRATION`, so a fourth embedder gets coverage automatically); refused an `api/` test (`services.py` never touched the embedder then; changes at slice 7) and a
`test_base.py` (the template is exercised through two concrete providers); **all 9 new invariants mutation-tested and caught**, including "Cloudflare vectors are matched by
position" and "a text over the input limit costs no request".

### Slice 1b, second pass — five embedders, and Cohere is the surprise

*Google and Cohere were added at the user's request after the three-way pass; **the tables above are superseded by this one.** 290 unit · 49 api · 7 integration · 24 smoke, ruff
clean; all 14 new invariants survived mutation testing.*

| | codestral | cohere v4 | bge-base | mistral | **gemini-embedding-001** |
|---|---|---|---|---|---|
| dim | 1536 | 1536 | 768 | 1024 | **3072** |
| recall@1 | 0.412 | **0.529** | 0.294 | 0.353 | **0.529** |
| **recall@5** | 0.941 | 0.882 | 0.824 | 0.765 | **1.000** |
| **recall@10** | 0.941 | **1.000** | 0.882 | 0.882 | **1.000** |
| **MRR** | 0.613 | **0.723** | 0.523 | 0.529 | 0.690 |
| tokens, same corpus | 14,979 | **13,412** | 39,936 | 19,143 | **not reported** |
| platform | Mistral | Cohere | Cloudflare | Mistral | **Google ✅** |

The Google column was scored on **2026-08-27** once the exit IP stopped being refused (`artifacts/2026-08-27_22-23_google-embedder-scored.md`); `codestral-embed` re-run as a **control**
reproduced its 2026-08-20 numbers exactly (0.412 / 0.941 / 0.941 / MRR 0.613), so the harness is not the variable.

#### Cohere is the best ranker, and it stays last anyway

`embed-v4.0` wins recall@1 (+11.7 over codestral) and MRR (+11.0), is the only model with **perfect recall@10** (never worse than 7th on any query), and the most token-efficient.
It sits last in `MIGRATION` because the reason was never quality: its 1,000 calls/month are **one bucket shared by chat, embed and rerank**, Cohere is the reranker primary, and a
corpus embedded there keeps spending the rerank budget on every query forever (confirmed by `x-endpoint-monthly-call-limit: 1000`). **A model can be the best one and still be the
wrong one; rank by the resource that runs out, not only by the score.** Under retrieve-50-rerank-to-10, **recall@10 matters more than @5**, on which Cohere is perfect and codestral is
not; slice 6 had to re-read this table once a reranker existed.

#### Google was scored on 2026-08-27, and it leads on recall

**`gemini-embedding-001` is the only model that put every target in the top 5** (recall@5 1.000 vs codestral 0.941 and Cohere 0.882; recall@10 1.000 tying Cohere; Cohere keeps MRR,
0.723 vs 0.690). **`D2`, our worst known miss: codestral rank 41 (returned the line that CALLS `clip_grad_norm_`), gemini rank 3 (returned the config block)** — so a better embedder
weakened part of the argument for hybrid search: slice 5 must re-check it on top of Google, and not keep it if it does not move recall@5. > **A weakness you designed a feature around
may belong to the model, not the method; re-run the motivating case after any model change.** Two costs only Google carries: (1) **it cannot be indexed as a plain `vector`** (3072
dims is above pgvector's 2000 index ceiling, measured on the real project; needs an **expression index on `(v::halfvec(3072))`** or `outputDimensionality: 1536`, a *different
vector* whose recall must be re-scored — a slice 4 decision, settled in the pgvector gate below); (2) **it reports no usage** (`batchEmbedContents` returns no usage block, so
ingest token cost can only be estimated).

#### The query/document asymmetry became real, and it may explain Cohere's lead

Cohere's v2 embed **requires** `input_type`, so the distinction could no longer be deferred: `embed()` takes `task: Task = "document"`, translated per provider — Cohere
`input_type: search_document`/`search_query`, Google `taskType: RETRIEVAL_DOCUMENT`/`RETRIEVAL_QUERY`, Mistral and Cloudflare ignore it. **The only provider that has the asymmetry
has the best ranking quality**: one data point, the first evidence that it is worth paying for. `task` was deliberately not added in the first pass (a parameter with no working
consumer is dead code; one two providers translate is an interface).

#### Google shipped unverified, on purpose — and it was proven right 2026-08-27

> **The quarantine is lifted:** `pytest tests/smoke/test_embedders.py --run-smoke` reported **`XPASS` for `gemini-embedding-001`** (the signal the `xfail(strict=False)` was built to
> send), `dim = 3072` was **observed** so `_validated` never had to fire. The `xfail` marker was then deleted (2026-08-30, commit `7b4c1db`; smoke 5 passed, and a mutation
> pointing Google at a dead model turned it red where the old marker reported a silent `xfailed`). Unmeasured still: whether `batchEmbedContents` reports usage, and the real batch
> ceiling. **What this vindicates is the *shape* of the gamble, not the gamble:** ship an unproven provider only when its first real call must either work or crash, never when it can
> quietly half-work.

`GoogleEmbedder` was written from documentation before it had ever returned a vector, at the user's explicit instruction, against the rule *an unproven provider is not a provider*;
it was safe because `dim=3072` was documented and `_validated` raises loudly on a wrong width, the smoke test was `xfail(strict=False)` (as GLM-5.2), and every wire detail was pinned
by tests (key in `x-goog-api-key` never `Authorization`; **each text gets its own request object**; task → `RETRIEVAL_QUERY`/`RETRIEVAL_DOCUMENT`; all mutation-tested).

#### The registry test earned itself within the hour

`COHERE_API_KEY` was documented in `.env.example` and **not mapped in `smoke.yaml`**; `test_every_embedder_env_var_is_mapped_in_the_smoke_workflow` failed the moment Cohere joined
`MIGRATION` (the shape of the 2026-08-11 `OPENROUTE_API_KEY` typo, caught before it ran). Side lesson: an anchor edit failed twice because `smoke.yaml` **ended without a trailing
newline**; text files that end mid-line break naive patching.

#### Mutation testing found a decision that lived only in a comment

13 of 14 mutations were caught; the survivor: pointing BGE at `MISTRAL_API_KEY` did **not** break `test_no_single_platform_can_empty_the_migration` (five embedders across four
platforms still satisfy it). The property claimed in `registry.py` was stronger and untested — *BGE sits second because it is the only early entry on a different platform* —
so `test_the_two_best_embedders_do_not_share_a_platform` pins it (a migration is not a fallback: recovering means re-embedding by hand, so if the top two die together that step falls
on an unmeasured, blocked or rerank-budget model). > **The mutation revealed a missing test. A design decision that lives only in a comment is a decision nothing defends.**

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

All eight rows live inside `_raw_vectors`, `_payload` and `_prompt_tokens`; nothing leaked into the shared template, the test of whether `base.py` was cut in the right place.
