# Step 1, slice 5: keyword search and fusion

[Docs home](../README.md)


**UPDATE 2026-11-24 (D142):** `keyword_search` (`ts_rank`) and `weighted_rrf` are deleted: only `bm25_search` and `score_fusion` run. The text below is the history. See [the cleanup](../step2/34-cleanup-before-slice-12.md).

## Slice 5 — the theory, recorded 2026-09-06

> **UPDATE (slice 8, 2026-09-16/19): the decision recorded below was OVERTURNED.** Slice 5's "not one fusion setting improved
> recall@50" described two SATURATED Python corpora; on the unsaturated `golang/geo` every wRRF setting improved `r@50`. **Fusion is
> now ALWAYS ON on the large-corpus path, and the method is score fusion `a = 0.85`, not wRRF** (see SLICE 8 — MEASURED). What
> survives from this slice is the keyword channel itself, BM25 as its algorithm, the safe-query builder and the rules below.

*Session 18 wrote no source: the keyword half of hybrid search was **probed against the real database first**, because the whole
plan rested on one sentence that had been written and never run.*

### The claim that was an assumption, and it is TRUE

*"A keyword search matches `clip` and `norm` because they are inside the identifier."* Measured: Postgres labels `_` a **blank**, so
`CLIP_NORM = 1.5` becomes `'clip':1 'norm':2 '1.5':3`, and stemming closes the other side (the query word `clipped` stems to
`clip`); both steps are needed. **A dot is NOT a blank:** `torch.nn.utils.clip_grad_norm_(params, 1.5)` becomes
`'torch.nn.utils.clip' · 'grad' · 'norm' · 'param' · '1.5'` (the parser reads a dotted path as a host name and keeps it whole).

### The operator matters more than the ranker — 0 of 17, then 14 of 17

The first probe scored **0 of 17**, which reads like "keyword search does not work on code": it was the probe. `plainto_tsquery`
joins terms with `&`, so one chunk must hold every word of the sentence. Converting the lexemes to an **OR** query changed nothing else
and took recall@5 from 0.000 to 0.824. **A zero result is a result about your instrument until you prove otherwise.**

### The measurement — 82 chunks of `B_train.py`, the same 17 graded queries

| | r@1 | r@5 | r@10 | MRR | **`D2`** |
|---|---|---|---|---|---|
| **cosine** (codestral) | **0.412** | **0.941** | 0.941 | **0.608** | **46** |
| `ts_rank` (OR) | 0.235 | 0.824 | 0.941 | 0.458 | **4** |
| `ts_rank_cd` (OR) | 0.353 | 0.765 | 0.941 | 0.486 | 5 |

Keyword search alone is worse, and that is not the point: the two **fail on different queries**, the only condition under which
fusing can pay (cosine fails `D2`, the constant `CLIP_NORM = 1.5`, at rank 46; keyword fails `D14`, a meaning query with no shared
identifier). Both return `_backprop_with_scaler`, the code that *calls* `clip_grad_norm_`, at rank 1 for `D2`: keyword search cannot
tell the constant from the call, it only sees words, but it ranks the constant 4th instead of 46th.

### Postgres has NO BM25, and the reason is structural

`ts_rank(tsvector, tsquery)` receives **one document**: no corpus, so no `N` or `n_t`, so **IDF is impossible by construction**
(length normalization is an optional argument, off by default; `ts_rank_cd` adds only cover density).

$$
\text{BM25}(q,d) = \sum_{t \in q} \text{IDF}(t)\cdot
\frac{f(t,d)\,(k_1+1)}{f(t,d) + k_1\left(1-b+b\,\frac{|d|}{L}\right)}
\qquad
\text{IDF}(t) = \ln\frac{N-n_t+0.5}{n_t+0.5} + 1
$$

`f(t,d)` occurrences of term `t` in `d` · `|d|` its length · `L` the average length · `N` documents · `n_t` documents holding `t` ·
`k_1 ≈ 1.2` saturation · `b ≈ 0.75` length normalization. The cost of no IDF is already visible: query `D6` matched 73 of 82 chunks (an OR
over common words matches nearly everything). **Supabase offers no real-BM25 extension** (`pg_search`, `pg_textsearch`,
`VectorChord-BM25` are all external or unavailable; ParadeDB itself calls doing it in SQL "very convoluted and very slow").

### BM25 BY HAND is now a scheduled experiment — the user's call, 2026-09-06

Compute it **in Python** over the stored tsvectors (one artifact is ~1,000-10,000 chunks; `N` and `n_t` are one pass; nothing is added
to the schema). Slice 5 therefore measured three keyword rankers: `ts_rank`, `ts_rank_cd` and BM25 by hand.

### The fixture is SATURATED, so it may REJECT and may not CONFIRM — 2026-09-07

*The user challenged the first rule the day it was written, and was right.* Cosine already scores 16 of 17 on recall@5, so that metric
can only take 0.882 / 0.941 / 1.000 (one query = 5.9 points) and a genuinely better hybrid would report "no change". The queries also
carry leakage (17 queries, one author, one Python file; `D2` is the motivating case AND the test). It can still **catch a large
regression** and **confirm one large single fact** (`D2` from place 46 to 4). **The corrected rules:** (1) this fixture may REJECT,
never CONFIRM (if the mix ties or helps a little, keep the code and let slice 8 decide; deleting is the hard thing to undo); (2) rank on
MRR and the PLACE of the correct chunk, report recall@5 but do not decide on it; (3) write a second query set before slice 8; (4) BM25
ships only if it clearly beats the better of `ts_rank` / `ts_rank_cd`; (5) measure the mix first, BM25 second; (6) re-check `D2` on the
embedder that wins slice 8 (`gemini-embedding-001` already ranks it 3rd where codestral ranks it 46th).
**A saturated test cannot measure an improvement; before trusting a number to make a keep-or-delete decision, ask how much room it
has left to move.**

## SLICE 5 MEASURED — 2026-09-07: vector ships, wRRF is a named candidate

*The user refused a decision taken on one fixture. Two corpora × two embedders = four runs, 62 graded queries, 82 fusion settings, no
generation quota.* Reproduce with `scripts/retrieval/score_hybrid.py` (**a measurement you cannot repeat is a number, not a result**).

### What was built

A **second corpus**, `psf/requests` at `dae7ef6` (`src/requests/*.py`, 19 files, 6,394 lines, **335 chunks**; real, third-party, not
machine learning; the corpus is NOT committed, fetch it); **45 new queries** (`data/samples/requests_http/queries.json`, frozen before
any measurement) labelled by `asks` (constant · behaviour · error · api · structure) and `wording` (**named** = shares a word with the
code, **paraphrase** = deliberately avoids it); **BM25 by hand** over Postgres's own lexemes; and fusion by RRF, weighted RRF, min-max
score fusion, CombMNZ and two new methods. **A query file needs a `file` field** (line 186 exists in most files of a 19-file corpus).

### The result that decides it: recall@50 is already at the ceiling

The pipeline retrieves 50 and then reranks, so recall@50 gates what the model can ever see: vector alone scored quora/codestral
1.000, quora/google 1.000, requests/codestral 0.978, requests/google 1.000 — **123 of 124**. The single miss (`R45`, "how is the body
handed back a piece at a time...") was not rescued by BM25 either (vector 67, bm25 NOT FOUND). **Across all 82 fusion settings not one
improved recall@50 on any run.** *Before tuning a number, check how much room it has left.*

### The two fixtures gave OPPOSITE answers, which is the whole point

Vector MRR 0.608 (quora) / 0.646 (requests); RRF k=10 gave 0.699 (**+15%**) on quora and 0.564 (**-13%**) on requests. Deciding on 17
queries would have shipped it.

### The comparison table — averaged over all four runs

| method | r@50 | r@10 | r@5 | MRR | worst single run vs vector |
|---|---|---|---|---|---|
| **vector alone** | **0.994** | 0.930 | 0.871 | 0.645 | +0.000 |
| bm25 alone | 0.926 | 0.804 | 0.678 | 0.475 | **−0.267** |
| **wRRF k=5 w=0.15** | **0.994** | 0.935 | **0.891** | 0.655 | **+0.000** |
| wRRF k=10 w=0.1 | 0.994 | 0.930 | 0.876 | **0.657** | +0.000 |
| wRRF k=20 w=0.05 | 0.994 | 0.930 | 0.876 | 0.656 | +0.000 |
| wRRF k=60 w=0.5 | 0.994 | 0.943 | 0.830 | 0.644 | −0.118 |
| **wRRF k=60 w=1.0** (plain RRF) | 0.978 | 0.915 | 0.797 | 0.621 | **−0.124** |
| score a=0.85 | 0.994 | 0.941 | 0.882 | **0.671** | −0.059 |
| RESCUE m=5 after=20 | 0.994 | 0.930 | 0.871 | 0.645 | +0.000 |

**Read the last column first** (an average that hides a −0.124 is the same mistake as a fixture that hides a blind spot). The first
report said "hybrid hurts" because of one badly chosen setting: **a default is not a measurement, and a bad default is not a verdict
on the method** (pgvector's `ef_search = 40`, RRF's `k = 60`). **Nine settings are never worse than vector anywhere:** wRRF with small
`k` (5-30) and a small keyword weight (0.05-0.2), and RESCUE `m=3/5, after=20/30`; best, `wRRF k=5 w=0.15`, is about **one query per
fixture** (`r@5 +0.020`, `MRR +0.010`).

### BM25 beats both Postgres rankers, measured

On requests: BM25 r@1 0.400, r@5 0.533, r@50 0.911, MRR 0.479 vs `ts_rank` 0.311 / 0.511 / 0.867 / 0.416 vs `ts_rank_cd` 0.178 / 0.578 /
0.911 / 0.327. The missing IDF is a real, measured cost, every safe fusion setting uses BM25, and BM25 alone still loses to vector.

### Where keyword search actually wins: `constant` queries, and only those

MRR by question kind (requests, codestral), vector vs bm25: constant 0.354 / **0.423**, error 0.600 / 0.612, behaviour 0.787 / 0.657,
api 0.456 / 0.175, structure 0.926 / 0.426. `constant` is the `CLIP_NORM` shape ("what is this value set to"). It was read then as a
routing signal; **slice 8 later found the routing signal DEAD** (every question kind positive once the reranker was a good one).

### Two fusion methods invented here

**RESCUE** (keyword may PROMOTE, never DEMOTE: RRF pushed quora `D14` from place 5 to 27 because rival chunks collected points from
both lists) never hurts and never helps; **ADAPTIVE RRF** (weight the keyword list by `1 - matched/N`; `D2` matched 7 of 82 and was right,
`D6` 73 of 82 and was noise) won on quora, middling on requests, not carried forward.

### Corrections this run produced

`gemini-embedding-001` is NOT clearly better than `codestral-embed` (MRR 0.674 vs 0.608 on quora, level on requests 0.650 vs 0.646, worse
recall@10 there 0.844 vs 0.933, better recall@50 1.000 vs 0.978). The `D2` argument for hybrid was weaker than it looked: `D2` sat at place
46 of 82, *inside* the top 50.

### THE DECISION — 2026-09-07, the user's call

(1) Vector search alone is the retrieval path for now. (2) BM25 is the keyword algorithm if a keyword channel is ever switched on (not
`ts_rank`, not `ts_rank_cd`). (3) wRRF with small `k` and small weight is a NAMED CANDIDATE for slice 8, allowed to replace vector search
if it wins there. (4) Nothing is decided by this experiment: two Python corpora, 62 queries, one author, and **no reranker**. Slice 8
had to test many corpora, many models, **with the reranker** (the gain is all inside the top 50, which the reranker reorders), large
corpora (at 10,000 chunks a top-50 window is 0.5% of the corpus, not 15-61%) and the two BM25 knobs never swept.
**The gain is real, small, and in the region slice 6 overwrites: not a reason to delete it, a reason not to claim it yet.**

### The four hyperparameters, and the three methods that were lost — 2026-09-07

`k` (swept 5-60, uses 5) and the keyword weight (0.05-1.0, uses 0.15) were swept; **`k1` (1.2) and `b` (0.75) were textbook guesses never
swept** (`--sweep-bm25` now varies them). First result (quora/codestral, k1 ∈ {0.9, 1.2, 1.6, 2.0}, b ∈ {0, 0.3, 0.75}): BM25 alone MRR
0.465 → 0.492, the fused winner 0.619 → 0.624 (far under one query), recall@50 unchanged; **tuning the keyword channel moves the keyword
channel and barely the fused result.** My prediction that `b` would be flat was wrong (the lowest `b` gave the best fused MRR; possibly
noise). **Score fusion, CombMNZ and ADAPTIVE had lived in a session scratchpad and were lost**, so three table rows could not be reproduced
by the repository that reported them; restored 2026-09-07, each re-deriving its number (ADAPTIVE's best MRR is **0.732 on quora/google**
and 0.700 on quora/codestral: **name the corpus AND the embedder beside every number**). **The rule: judge a method by how many
independent ways it was shown better, never by its best single number.** BM25 won on every metric, on both corpora, with a mechanism
(no IDF in `ts_rank`); score fusion had the best average MRR, one run losing recall@50 and no mechanism: a number, not evidence.

## Slice 5 — DONE 2026-09-08

*The code. **595 passed; 27 mutations, every one real.** Nothing called it — that IS "off by default": no flag, because a flag nobody
reads is dead configuration (slice 7 later gave it a caller, slice 8 switched it on).*

### What shipped

`store/schema.sql` (one generated `tsvector` column + one GIN index) · `store/keyword.py` (`keyword_search()` using `ts_rank`, and
`bm25_search()`, ours) · `retrieval/fusion.py` (`weighted_rrf()`, pure, no database; `retrieval/` gained its first part that outlives the
throwaway selector) · `store/defaults.py` (`BM25_K1 = 1.2`, `BM25_B = 0.75`).

### Probing the real database first found THREE defects, all silent

Adversarial input handed to the benchmark's expression before any product code (its 62 queries are hand-written English; a real query is
whatever the user types): `api.github.com:443` **CRASHED** (`to_tsquery` reads `:` as a weight marker); `http://x.com/p?a=1&b=2` silently
**reinstated the AND** that scored 0 of 17; `please` silently missed. The fix is two words, each load-bearing:

```
to_tsquery('simple', array_to_string(array(
    select quote_literal(lexeme)
    from unnest(tsvector_to_array(to_tsvector('english', %s))) as lexeme
), ' | '))
```

**`quote_literal`** makes a quoted lexeme inert (`:` and `&` inside a token are not operators). **`'simple'`, never `'english'`**: the lexemes
are already stemmed, and stemming them again can change them so they no longer match what is stored (`pleas` → `plea`; `to_tsvector('english',
'please read this') @@ to_tsquery('english','plea')` is False, with `'simple','pleas'` True; 1 word in 11 drifted). The stored side stays
`'english'`. **A query builder proven on your benchmark is proven on your benchmark; probe the edge before promoting a script to a module.**
One edge left alone: a URL token still re-parses into a *phrase* (`<->`) inside its own term (not an AND across concepts, and the stored side
tokenizes identically); removing it would drop `tsquery`, the GIN index and `ts_rank`.

### What the keyword channel costs in storage, measured

On 1,090 real chunks: **~1,022 bytes per chunk** (column 624, GIN index 398), +162% on the text alone but only **+11.6% of a 1536-dim row** (two
10k artifacts 177 MB → 197 MB) and +21.2% of a 1024-dim row: affordable against the 500 MB tier. (A first run on 304 chunks reported 1,401
bytes/chunk: page rounding on a table of 30 pages; re-measured before it was written down.)

### The tests, and what mutation testing found

36 new tests (17 fusion unit, 15 keyword + 2 schema `database`, 2 error-boundary); **no API or smoke test** (no route reaches keyword search).
Mutation testing found two of my own tests wrong: `test_..._when_scores_tie` fused `[3,1,2]` with `[3,1,2]`, three different scores, so
there was no tie (same shape as `test_a_word_is_never_cut_in_half`), and defeating the artifact filter inside `_MATCHES` broke nothing because
`_HITS` filters by artifact too (fixed by making the other artifact score **higher** and start at index 10). **A second guard downstream can
make a broken guard upstream look fine; test the one you mean to test.**

### The review pass — one guard added, one weakness recorded

`tests/unit/test_error_boundaries.py` reads every import and `except` in `labpilot/api/` and fails when an adapter the API imports can raise
something nothing catches (adding `from labpilot.store import UnknownArtifact` to `services.py` turns it red, alone). It also found six
`sources/` error types nothing in `api/` catches (latent, since `chunk_source` had no caller), listed by name in `ALLOWED_TO_ESCAPE`
following the `OUTPUT_TOO_SMALL` pattern (a deliberate gap is documented, an accidental one is red). **A weakness in slice 4's tests:**
`test_store_search.py` numbered its chunks `0..3`, which are also valid row positions, so `select row_number() - 1` instead of `chunk_index`
left the whole file green; only `test_the_two_channels_rank_the_same_id_space_and_fuse` (ids from **100**) fires alone. **A fixture
numbered from zero cannot tell an id from an index.**

### What slice 5 deliberately did NOT build

No caller (slice 7 wired it), no `avg_tokens` column, no `ts_rank_cd` (lost on every run), no flag.

### Honest limits

`ts_rank` is shipped as the loser, kept so slice 8 can compare in product code; `bm25_search` costs 4-5 round trips against
`keyword_search`'s one (Postgres cannot do IDF; unmeasured on a real corpus, `ts_rank` is the existing fallback); `_CORPUS_CACHE` is unbounded
(each entry tiny); the generated column is computed on every insert (ingest slightly slower, not measured).
