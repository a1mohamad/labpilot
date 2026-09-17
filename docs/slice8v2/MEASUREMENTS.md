# Every measurement this project has asked for, and where it is covered

CLAUDE.md names its open questions in about fifteen different places, written
down over eight slices. Slice 8's first run answered nine of them and the rest
were never collected into one list, so "did we measure everything" could not be
answered by reading.

This is that list. **A row is only `DONE` when a number exists in
`RESULTS.md` with the run behind it.** Rows marked `NOT DOING` say why, which
is the part that stops a gap turning into an oversight.

Numbering is mine; the "asked in" column points at the section of CLAUDE.md
that owes it.

---

## A. Slice 8's own nine jobs

| # | measurement | asked in | phase | state |
|---|---|---|---|---|
| A1 | **embedder ranking** on many corpora, more than one language | slice 8 decides the embedder | 6 | ✅ |
| A2 | **reranker ranking** - chain 3's order | slice 8's job grew | 5 | ✅ |
| A3 | **exact vs HNSW** on real artifacts, real instance, plan asserted | slice 8's job grew #3 | 9 | ✅ |
| A4 | **end-to-end TIME** - embed, search, rerank, generate | slice 8's job grew #4 | 10 | |
| A5 | **merged vs per-side** reranking | slice 8's job grew #5 | 7 | ◐ quora done (50% slots, identical); two-corpus case interrupted — RESUME 4.4 |
| A6 | **`SEARCH_LIMIT` and `VECTOR_TOP_N` swept JOINTLY** | slice 8's job grew #6 | 5c + 8 | ◐ the WINDOW is still one corpus — see RESUME 4.2 |
| A7 | **where the cut goes** - before or after the reranker | slice 8's job grew #7 | 5c | ◐ inherits A6's gap |
| A8 | **per-tier rerank window vs a global one** | section 14.3 | 5d | … every corpus ran at window 50 |
| A9 | **does the report need the strongest tier** | section 11.9 | 8b | ✅ |

## B. Fusion - slice 5's named candidate

| # | measurement | asked in | phase | state |
|---|---|---|---|---|
| B1 | **wRRF `k` and weight**, a real grid, every corpus | the four hyperparameters | 4 | ✅ |
| B2 | **BM25 `k1` and `b`** - never swept, textbook guesses | the four hyperparameters | 4b | ✅ |
| B3 | **all five fusion methods** - wRRF, RESCUE, score, CombMNZ, ADAPTIVE | three methods that were lost | 4 | ✅ |
| B4 | **fusion re-measured WITH reranking on** | slice 6 measurement 4 | 5e | ◐ |
| B5 | **recall@50 on a LARGE corpus**, where a 50-window is 0.5% | slice 5 decision, "large corpora" | 4c | ✅ |

## C. Reranking - slice 6's open ends

| # | measurement | asked in | phase | state |
|---|---|---|---|---|
| C1 | **the skip gate** `tau` | slice 6 measurement 3 | 5 | ✅ |
| C2 | **`RERANK_TOP_N` vs `VECTOR_TOP_N`** - two numbers, not one | section 14.2 | 5c + 8 | ✅ |
| C3 | **`rerank-3`** (non-lite) - never scored anywhere | slice 8 §8 | 5d | |
| C4 | **Cohere**, the chain primary | slice 6 "what it may not conclude" | 5d | |
| C5 | **a NEWER local reranker** (bge-v2-m3 / Qwen3) - the only one that BATCHES | slice 6, the cheap answer to Step 2's cost | 5f | |
| C6 | **the chunk header's effect** on reranking (`--no-header`) | slice 6 confounds | 5g | |
| C7 | **decline rate** - a model that abstains is invisible in MRR | slice 6, gemma-26b | 5 | ✅ |

## D. Embedders

| # | measurement | asked in | phase | state |
|---|---|---|---|---|
| D1 | **`gemini-embedding-2`** scored on OUR fixture, not MTEB | registry note | 6 | ◐ only 3 corpora, 2 saturated — UNRESOLVED, not 'worst'. RESUME 4.3 |
| D2 | **BGE's three owed numbers**: speed, strength, real tokenizer ratio | section 6 | 6b | ✅ |
| D3 | **ingest TIME per embedder**, against `embedding_minutes()` | section 9, open debt | 6c | |
| D4 | **Google's real quota** - texts or calls | F4 | 6c | ✅ |
| D5 | **Cohere's real tokens/minute** | F3 | 6c | ✅ |
| D6 | **`MAX_BATCH_SIZE` is a Mistral constant** - does it break others | F1 | 6c | ✅ |
| D7 | **query/document asymmetry** - does `task=` actually matter | slice 1b | 6d | **NEW** |

## E. Chunking - the permanent decisions nobody has measured

| # | measurement | asked in | phase | state |
|---|---|---|---|---|
| E1 | **chunk size `s`** - "do not tune s by feeling. Change it, re-run" | chunking | 12 | **NEW** | ✅ |
| E2 | **overlap `o`** | chunking | 12 | **NEW** | ✅ |
| E3 | **the context header's value** - "measure the free header first" | chunking, contextual retrieval | 12 | **NEW** | ✅ |
| E4 | **small-to-big / neighbour expansion** | chunking, small-to-big | — | NOT DOING |

## F. Prompt and generation

| # | measurement | asked in | phase | state |
|---|---|---|---|---|
| F1 | **how many chunks to SEND** - the generation half | slice 6 measurement 2 | 8 | ◐ first answer REJECTED (one 100-chunk fixture); rebuilt as score_answers.py, run INTERRUPTED — RESUME 4.1 |
| F2 | **generated queries vs hand-written** - the domain-lock fix | the fixed checklist is domain-locked | 13 | **NEW** |
| F3 | **`estimate_tokens` accuracy** against providers' own counts | token budget | 6c | **NEW** | ✅ |
| F4 | **model blind spots are disjoint** - vary the model, not the seed | multi-pass | 8b | |
| F5 | query **fan-out**, six sub-queries into one rerank | six queries one rerank | — | NOT DOING |

## G. Analyses that cost nothing and were never done

All of these re-read data the phases above already produce. They are **NEW**,
they are mine, and they are where I expect the most useful findings, because
every earlier run had only three corpora and could not group by anything.

| # | measurement | why it is worth doing |
|---|---|---|
| G1 | **by FORMAT** - code vs prose vs notebook | the loader path has never been scored; `papers` already beats vector with BM25 |
| G2 | **by SPLITTER** - AST vs recursive vs cells vs pages | isolates "the language" from "having no splitter", which the first run confused |
| G3 | **by chunk SIZE**, across corpora | a rerank tier's usable window is set by chunk size, so this predicts reachability |
| G4 | **by query WORDING** - named vs paraphrase | the fixture labels it and nothing has ever read the label |
| G5 | **by corpus SIZE**, one corpus sliced | separates size from language, which three corpora could not |
| G6 | **saturation-aware re-reading** of slice 5 and 6's conclusions | 5 of 13 corpora cannot show a gain; those are the ones the old decisions rested on |

---

## What is deliberately NOT measured, and why

- **E4 small-to-big / neighbour expansion** and **F5 fan-out** are *designs
  that do not exist in the code*. Measuring them means building them first, and
  both are Step 2 features. Slice 8 measures what ships.
- **Multi-pass self-consistency** needs sampling, and `temperature: 0` is a
  standing rule for comparability. Already settled on 2026-08-17.
- **`ts_rank_cd`** lost on every run of the slice 5 sweep and is kept only so
  its claim stays reproducible.
- **The two Gemma tiers as GENERATORS.** They are measured as rerankers here;
  whether they can write a report is a separate question with its own budget.

---

## THIRD SESSION, 2026-09-17 — what moved

Exit `80.240.20.89`, **AS20473 The Constant Company** (Vultr, Frankfurt);
Google answered **200** on both keys.

### The instrument was found broken before anything new was trusted

`PairScores` synthesised a score from a listwise reranker's ORDER and cached it
per pair, so two calls for one query collided. See **G14**. Five of thirteen
rerank corpora and all three merged benchmarks were void; the 13 clean caches
were migrated for free and verified against a recorded number
(`cobra` 0.634 → 0.794, `calls: 0`).

**Rows that had to be re-measured because of it:**

| # | was | now |
|---|---|---|
| A2 | reranking helps 10 of 13, mean +0.122 | re-run on the 5 void corpora |
| A3 | `SKIP_MARGIN = 0.05` | inherits A2's corpora |
| A5 | merged never starves a side, 0 of 20 | **overturned — see below** |
| A6/A8 | the window sweep's `w=100` row | void, being re-run |
| B4 | fusion under reranking | inherits A2's corpora |

### Rows that CLOSED this session

| # | measurement | result |
|---|---|---|
| **F1** | how many chunks to SEND | ✅ **G15** — dilution is real, peaks at **N=20**, and N is a **COUNT** not a coverage share (cv 0.41 vs 1.03 over a 15× size range). `RERANK_TOP_N = 10` per side is vindicated; `VECTOR_TOP_N = 25` is too large |
| **G4** | by query WORDING — the label nothing read | ✅ **G16** — paired over 13 corpora, BM25 loses on both groups and loses **half as much** on `named`. The premise is true in direction, false in magnitude |
| **A5** | merged vs per side | ✅ **merged starves a side on 4 of 17 queries** (was reported as 0 of 17 by the broken instrument) for **identical** quality, 0.824 either way. Per side is correct, and now it has evidence |

### Still open at the end of this session

| # | measurement | why it is not done |
|---|---|---|
| A4 | end-to-end TIME | not run — `WARN_MINUTES = 2.0` is still a guess |
| A6/A8 | `SEARCH_LIMIT` window sweep | re-running; the first run's answer is void |
| C3 | `rerank-3` (non-lite) | never scored anywhere |
| C4 | **Cohere**, the chain PRIMARY | scored on one corpus |
| C5 | a NEWER local reranker | needs a model download; `ms-marco-MiniLM` is 2021 and already measured harmful |
| C6 | the chunk header under reranking (`--no-header`) | died on quota in the second session |
| D1 | `gemini-embedding-2` | 3 corpora, 2 saturated — unresolved, not "worst" |
| D3 | ingest TIME per embedder against `embedding_minutes()` | — |
| F2 | generated queries vs hand-written | the domain-lock fix, unmeasured |
| F4 | model blind spots are disjoint | — |

### Two production defects, still unfixed, and one of them breaks a SHIPPED decision

- **`MAX_BATCH_SIZE = 96` is a Mistral constant with a global name.** It is
  `floor(50,000 / 510)` from codestral's per-minute tokens, and it is used in
  three places as though it were universal. At the measured mean of 341.6
  tokens per chunk, 96 Google texts is ~32,800 tokens against a 30,000/minute
  ceiling — refused on the **first batch**. The halving fallback in
  `embed_batches()` matches on the word *token*, and Google's refusal does not
  contain it, so it **raises instead of halving**.

  This is not theoretical any more: decision **A8 shipped** `SMALL_CORPUS_CHUNKS
  = 500`, which sends every small corpus to Google first.

- **`embedding_minutes()` counts HTTP calls where Google counts TEXTS**, and
  models no daily request budget at all. It reports ~118 minutes for a
  10,000-chunk Google ingest; the truth is **ten days**.

  The design both need: `max_batch_size` and the unit of account move onto the
  embedder (`Rate` / `Spec`) instead of living in a module-level constant, and
  `Rate` gains a daily **request** budget beside its daily token budget.
