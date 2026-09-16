# SLICE 8, SECOND RUN — the plan, written before any number

The first run (2026-09-16, `docs/slice8/`) is **not trusted and is not
inherited**. Two reasons, both the user's and both correct:

1. **Three corpora, and two of them were already used.** Every headline rested
   on one new fixture. A result measured on one corpus is a result about that
   corpus.
2. **The measurement was incomplete.** `VECTOR_TOP_N`, `RERANK_TOP_N`, the
   best `wRRF` parameters, the search window, merged-vs-per-side and the BM25
   knobs were all named as open by CLAUDE.md, and none of them was settled.

So every number below is produced again from the beginning. The old scripts
are reused where they are sound instruments; the old *results* are treated as
claims to re-test, never as inputs.

---

## The rules this run binds itself to, fixed before any data

Taken from CLAUDE.md, written here so they cannot be bent once numbers exist.

1. **Decision rules are pre-registered.** Each phase states what would make it
   choose A over B, before it runs.
2. **A saturated fixture may REJECT, never CONFIRM.** Report the headroom
   beside every metric: a corpus at `r@50 = 1.000` cannot show a gain.
3. **Judge a method by how many independent ways it was shown better**, never
   by its best single number. With twelve corpora the claim is "won on 9 of
   12"; an average is a summary, not evidence.
4. **Name the corpus AND the embedder beside every number.**
5. **A query may never contain the identifier it is looking for.** Enforced
   mechanically, not by good intention.
6. **Ground truth is stored as LINE NUMBERS**, so it survives re-chunking.
7. **Match the experiment to the tier's limit.** A tier that refuses a
   50-document window is measured at a window it accepts, on a corpus whose
   chunks it can take — never recorded as "it failed".
8. **`r@50` must not move when a reranker runs.** It is the free check that
   says the instrument is sound rather than the reranker miraculous.
9. **Every phase is timeboxed to 40 minutes.** A phase that overruns is cut
   down, not extended.

---

## The corpus zoo

Twelve corpora carry queries. Two more are scale-only, for the index and
timing work. The design target is **under 1,000 chunks** — the size LabPilot
actually meets — with two corpora above it, so the conclusions are shown to
survive scale.

| # | corpus | format / language | domain | est. chunks | source |
|---|---|---|---|---|---|
| 1 | `quora` | Python + Markdown | machine learning | 82 + 18 | committed |
| 2 | `requests` | Python | HTTP client | 335 | psf/requests |
| 3 | `geo` | Go | spherical geometry | 729 | golang/geo |
| 4 | `cobra` | Go | CLI framework | ~250 | spf13/cobra |
| 5 | `log` | Rust | logging facade | ~100 | rust-lang/log |
| 6 | `jq` | C | JSON processor | ~700 | jqlang/jq |
| 7 | `gson` | Java | JSON serialisation | ~1,200 | google/gson |
| 8 | `zod` | TypeScript | schema validation | ~1,500 | colinhacks/zod |
| 9 | `papers` | **PDF** | ML research papers | ~400 | arXiv, fetched |
| 10 | `notebooks` | **.ipynb** | applied ML | ~400 | the user's own |
| 11 | `docs` | **Markdown** | mixed project docs | ~150 | fetched repos |
| 12 | `docx` | **.docx** | mixed reports | ~60 | the user's own |
| — | `labpilot` | Python | this project | ~5,400 | committed |
| — | `svelte` | JS/Svelte | web framework | ~15,000 | sveltejs/svelte |

Nothing third-party is committed. Every corpus is fetched and pointed at by an
environment variable, exactly as `geo` and `requests` already are.

**What the zoo is designed to break.** Each corpus attacks one assumption the
project has been carrying:

- `cobra`, `log`, `jq`, `gson`, `zod` — **five languages with no AST
  splitter**, so `split_recursive` is measured five more times, not once.
- `papers`, `docx`, `notebooks` — **the loader path**, never scored at all.
  Prose chunks are shaped nothing like code chunks.
- `docx`, `log` — **tiny corpora**, where a 50-document window is most of the
  corpus and retrieval barely matters.
- `gson`, `zod` — **above 1,000 chunks**, where a window is 3% of the corpus.
- `notebooks` — the **user's own working style**, which is the real input.

---

## The phases

Each is one sitting, timeboxed. They run in order because each feeds the next.

### Phase 0 — preconditions and instrument control  *(30 min)*
ISP probe, keys, database. Reproduce one recorded number exactly, so a later
disagreement is a finding and not a drifted scorer. Make `CORPORA`
data-driven, so adding a corpus is a JSON file and not code.

### Phase 1 — build the zoo  *(3 × 40 min)*
Fetch the missing corpora, chunk them, and write a query fixture for each:
**20 queries, five categories, interleaved**, ground truth as line numbers.
Queries are drafted against the real chunk text and then **validated
mechanically** — resolvable, not too broad, and no identifier leakage.

### Phase 2 — embed once, cache forever  *(40 min)*
`codestral-embed` over every corpus. The secondary embedders are paced to
their own limits and run only where their limit allows.

### Phase 3 — the vector baseline  *(30 min)*
`r@1 / 3 / 5 / 10 / 20 / 50` and MRR, twelve corpora. This is the ruler
everything later is measured against, and it says which corpora are saturated
and must not be allowed to vote on a gain.

### Phase 4 — fusion, swept exhaustively  *(40 min)*
Free: no provider is called. Five methods × `k` × weight × `k1` × `b`, on every
corpus. **This is where "the best wRRF parameters" is answered**, and it is the
cheapest phase in the run, which is why it gets done properly this time.

### Phase 5 — reranking  *(3 × 40 min)*
5a a pointwise cross-encoder over every corpus, so window and `top_n` sweeps
cost nothing afterwards. 5b the listwise headline on every corpus. 5c the
window sweep. 5d the refusal-limited tiers, each on a corpus and a window it
can actually accept.

### Phase 6 — the embedder ranking  *(40 min)*
Quota-matched: the models with a daily text budget are scored on the small
corpora only, and that restriction is reported beside their score.

### Phase 7 — merged vs per-side reranking  *(40 min)*
Never measured. It needs a two-artifact pair, so pairs are built from the zoo.

### Phase 8 — how many chunks to SEND  *(40 min)*
The one question retrieval cannot answer, because `recall@N` only rises.
Measured on generation, against `EXPECTED.md`, which is the only objective
answer key this project owns.

### Phase 9 — exact vs HNSW, several sizes  *(40 min)*
On the real instance, plan asserted, at 100 / 300 / 700 / 1,400 / 5,400 rows.

### Phase 10 — end to end  *(30 min)*
What a real answer costs in seconds, and which stage owns the time.

### Phase 11 — the write-up and the code  *(40 min)*
Findings with their evidence, the two open production defects, and the code
change each decision implies.

---

## What this run may still NOT conclude

Written now, so it is not claimed later.

- **Twelve corpora is not a population.** They are the corpora one person
  could fetch in a day, weighted toward open-source libraries.
- **English only.** Every query and nearly every document is English.
- **One author for every query.** Drafted by one system, validated
  mechanically, spot-checked by hand.
- **Generation quality is measured on ONE fixture**, `quora_siamese`, because
  it is the only one with an answer key.
