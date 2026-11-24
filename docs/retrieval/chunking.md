# Chunking

[Docs home](../README.md)

## Chunking — decided 2026-08-13, built in slice 3

*The chunker written in slice 3 is the chunker Step 1 keeps. Nothing else in
slice 3 survives unchanged, so this one is worth writing properly.*

### Why it is the highest-leverage decision in RAG

A **chunk** is the atom of retrieval — you never get half of one.

```
bad embedder  + good chunks  →  works, a bit worse
good embedder + bad chunks   →  broken, with no fix downstream
```

If the answer is split across chunk 7 and chunk 8, **no** embedder retrieves it
and **no** reranker repairs it. **Chunking decides what is possible; everything
after it only decides what is chosen.**

### The numbers, and where each comes from

$$
s \approx 500 \text{ tokens} \qquad o \approx 50 \text{ tokens}
\qquad \text{hard cap } 510 \qquad \text{minimum } \approx 30
$$

| Constraint | Limit | Source |
|---|---|---|
| **Cohere auto-splits longer documents** | **≤ 510 tokens** | binds first — see Chain 3 |
| `gemini-embedding-001` max input | ≤ 2,048 | embedder tier 3 |
| Prompt budget `k · s ≤ B_in` | `k=10`, `B_in=20K` → `s ≤ 2,000` | token budget |
| A function must fit one chunk | ~40 lines of Python | our structure rule |

**510 tokens is about 40 lines of Python**, not 500 — a fact that is easy to get
wrong by an order of magnitude. The cap is **soft**: exceeding it does not fail,
Cohere splits the chunk itself and bills 2–3 documents instead of 1, which
silently breaks the rerank budget arithmetic by 3×.

### The overlap rule — a formula, not a guess

Let `f` be the length of an atomic fact that must never be cut, `s` the chunk
size, `o` the overlap. Chunks start at `0, s-o, 2(s-o), …`, so:

$$
f \le o \;\;\Longrightarrow\;\; \text{the fact is never split}
\qquad\text{and otherwise}\qquad
P(\text{split}) = \frac{f - o}{s - o}
$$

> **Overlap must be at least as large as the longest thing that must never be
> cut.**

LabPilot's facts are single lines and short sentences, `f ≈ 10–20`, so `o = 50`
gives `P = 0`. A whole training loop is `f ≈ 60`, giving ~2.2% split — which is
exactly why we split on the **AST** instead of trusting overlap, since a parser
gives `P = 0` for any block at any size.

**A bug that is a *missing line* can only be found in a chunk holding the whole
block.** A training loop cut between `loss.backward()` and the absent
`optimizer.zero_grad()` hides the bug in both halves.

Overlap costs a factor of `s/(s-o)` extra chunks — **+11%** at `s=500, o=50`
*(corrected 2026-08-14: this file previously said 25%, which is the figure for
`o=100`, not for the `o=50` it pins two paragraphs above)* — and means the same
text can be retrieved twice. **Deduplicate before building the prompt.**

### Signal dilution — why big chunks retrieve badly

A model, not a theorem, but it explains the sizing. With `α = f/s` the fraction
of the chunk that is the fact:

$$
\cos\big(E(q), E(\text{chunk})\big) \;\approx\; \alpha
$$

| `s` | `α` at `f = 20` | outcome |
|---|---|---|
| 100 | 0.20 | strong |
| **500** | **0.04** | usable |
| 5,000 | 0.004 | invisible |

**One line of signal inside a page of unrelated text is nearly invisible to
search.** This is the same effect as "lost in the middle", one stage earlier.

### Split on structure, never with a ruler

| File type | Split on | How |
|---|---|---|
| Markdown / paper | headers (`#`, `##`, `§`) | text scan |
| Python | functions and classes | `ast.FunctionDef` / `ast.ClassDef` |
| Notebook | cells | it is JSON — the author already chunked it. **Designed here, never built — it lands in [Step 1 slice 3](../step1/plan.md#step-1--the-plan-recorded-2026-08-20)** |
| anything else | recursive: `\n\n\n` → `\n\n` → `\n` → ` ` → chars | fallback |

Header or AST splitting comes **first**; the size cap is a **second** pass. A
section over 510 tokens is split again, repeating its header on each part
(`[paper.md · §4.2 · part 2/3]`). A class over the cap splits per method; a
method still over it splits on blank-line blocks, then fixed size.

**Chunks are not all the same size, and must never be padded.** Padding adds
noise and lowers `α`. Only two rules apply: **merge** below ~30 tokens, **split**
above 510, and leave everything in between exactly as it is. Uneven sizes are the
sign that you split on meaning.

### The chunk carries metadata — design it now

```python
text · source · start_line · end_line · side · artifact_id ·
chunk_index · embedding_model · dim
```

- `source` + lines → the citation `[train.py:42]`
- **`side`** (A = reference, B = implementation) → **without it, a paper claim
  retrieves the paper**, because a paper's sentences match a paper's sentences
  best. This is the most confusing bug in the project and it is one missing
  filter.
- `embedding_model` + `dim` → a mixed embedder is detected, not silently
  poisoning search (already required by Chain 2)
- `chunk_index` → neighbour expansion later

**Define every field in slice 3, even though slice 3 has no database.** A
dataclass costs nothing; adding fields after 2,000 rows exist is a migration.
This is the *"design against the roadmap"* rule applied literally.

### Context header — free, no LLM call

A chunk like `model.fit(X, y, epochs=100)` has a generic vector. Prepend a header
built from metadata you already hold while chunking:

```
[train.py · def train_epoch · lines 42-71]
[paper.md · §4.1 Training]
[baseline.ipynb · cell 23 · section: Model training]
```

Filename, last header seen, function name from the AST, cell number — **all
free**. The technique is called **contextual retrieval**. An LLM-written
one-sentence description per chunk is a Step 1 upgrade, and is the same
mechanism as the summarise-before-embed fix for cross-language comparison.

**Groq re-enters here — and only here.** *(Raised 2026-08-14.)* Groq was excluded
from the generator chain because its free TPM (6K–12K) is smaller than one 24K
comparison prompt, so a single request could never pass. **That objection does
not apply to chunk annotation**, where the prompt is one chunk in (~500 tokens)
and one sentence out. The cost is volume, not size:

$$
2{,}000 \text{ chunks} \times 530 \text{ tokens} \approx 1.06\text{M tokens}
\;\Rightarrow\; \approx 2.2\ \text{hours at 8K TPM}
$$

Acceptable in principle — ingest is offline — but it makes ingest ~6× slower than
embedding alone and adds 2,000 calls that can fail halfway. **Measure the free
header first.** Run the chunker on the sample pair and count how many chunks end
with an empty `label`; if that number is near zero, the LLM sentence is buying
nothing. The general lesson worth keeping: **a provider excluded on prompt size
may still be perfect for a small-prompt job.** Re-check exclusions against the
actual task, not against the reason they were first rejected.

**Where the empty label really comes from.** `_recursive` is reached three ways,
and only two of them lack a name: an unknown extension, and a Python file that
fails `ast.parse`. The common third case — the second-pass split of an oversized
function or section — **inherits the parent's label** and gains `part i/n`, so
the fallback splitter is far less anonymous than it first appears.

**But the splitter does not do the labelling.** *(Corrected 2026-08-14 — an
earlier version of this line said `split_recursive` takes a `label` argument.)*
`split_recursive` receives only a string and cannot know where it came from. The
chunker called it, so the chunker knows the parent, and only the chunker knows
the total needed for `part i/n` — it counts the returned list. **The splitter
cuts; the chunker names.** Measured on `B_train.py`, exactly three chunks end up
with no label, and all three are module-level code: the docstring and imports,
the config instantiation block, and the `if __name__` guard.

### Small-to-big — Step 1, but keep it possible

> **Embed something small. Return something large.**

Search with the precise unit, then expand before building the prompt — the
parent document, or chunks `i-1` and `i+1` (**neighbour expansion**, which is
what `chunk_index` is for). This dissolves the precision/context trade-off and
is what makes a missing-line bug visible. Not built in slice 3; made possible by
the metadata.

### Counting

$$
N = \left\lceil \frac{L - o}{s - o} \right\rceil
$$

At `L = 1,000,000`, `s = 500`, `o = 50` this gives ~2,200 chunks — the "~2,000"
used throughout the budget sections, now derived rather than guessed. Storage is
`N · n · 4` bytes ≈ 15MB at `n = 1536` — but ~123MB as Python lists of floats,
which is the whole reason the repo walk streams in batches of 100.

### Five failure modes to test against

| Failure | Example | Fix |
|---|---|---|
| **Orphan chunk** | `        return total_loss / len(loader)` | structure split + context header |
| **Split block** | loop cut before the missing `zero_grad()` | AST split, overlap, neighbour expansion |
| **Giant chunk** | a 900-line file with no functions | hard cap + recursive fallback |
| **Duplicate flood** | 40 near-identical config files | hash-dedupe at ingest |
| **Mixed sides** | a paper claim retrieves the paper | the `side` filter |

### What slice 3 must ship

`labpilot/ingest/` — a frozen chunk dataclass with the full field set, three
splitters chosen by extension, `estimate_tokens` reused from `_text.py` (no new
tokenizer dependency), and tests in the same commit for: a function is never
split · overlap is present and correct · a sub-minimum chunk is merged, not
stored · no chunk exceeds the hard cap · line numbers really point at the text ·
an empty file yields zero chunks, not one empty chunk · an unparseable file falls
back to recursive splitting instead of raising.

**Do not tune `s` by feeling.** Change it, re-run, and look at whether the right
chunk comes back. Chunking is measured, not guessed.

### What the chunker actually shipped — 2026-08-14

`labpilot/ingest/` is built and measured. **The selector is not** — that is the
remaining piece of slice 3.

| Module | Holds |
|---|---|
| `contracts.py` | `Piece`, `Chunk`, `Side` — imports nothing from `labpilot` |
| `defaults.py` | the four numbers, plus `MAX_CHARS` / `MIN_CHARS` in characters |
| `_recursive.py` | the separator ladder, the fallback |
| `_markdown.py` | header split |
| `_python.py` | AST split |
| `chunker.py` | picks a splitter, runs pass 2, attaches metadata |
| `__init__.py` | `chunk_file`, `chunk_bytes` — the only door |

**Two types, and the split is by reason to change.** A splitter sees only text,
so it returns a `Piece` (text, lines, label). The chunker knows the artifact, so
it produces a `Chunk` (adds source, side, artifact_id, chunk_index, header).

**The header is a field, never inside `text`.** `Chunk.embed_text` is the single
place they are joined. If callers joined them by hand, one would forget, that
chunk's vector would be weaker, and **nothing would raise** — the expensive kind
of bug. `text` stays an exact copy of the cited lines, which is what makes a
citation checkable at all.

**Overlap applies only to arbitrary cuts.** An AST or header boundary already
gives `P(split) = 0`, so overlap there would duplicate whole functions for no
gain. Only `_recursive` and the second-pass size split overlap.

**Character limits, not token limits, inside the loop.** `estimate_tokens` is
exactly `ceil(chars/3)`, so a token cap is an exact character cap. Compare
characters; never call the estimator in a loop.

#### Three things the measurement changed

1. **Merge forward, not backward — and decide by label.** The plan said "merge a
   sub-minimum piece into the previous sibling". The real file disproved it: a
   bare `class QuoraTokenizer:` line is a *header*, so it belongs with the method
   after it, not with the last method of the previous class. But pure forward is
   also wrong — a tiny *last* method would cross into the next class. The rule
   that handles both: **merge with the neighbour sharing more of the label,
   ties go forward.** Guarded so a merge can never exceed the cap.
2. **Decorators must be included by hand.** `node.lineno` points at the `def`
   line, not at `@decorator`. Use `min(node.lineno, *decorator linenos)` or
   `@torch.no_grad()` is orphaned into the previous chunk.
3. **A `#` inside a fenced code block is not a header.** Track ``` and ~~~
   fences, or every code comment in a Markdown file becomes a section boundary.

#### Measured on the sample pair

| | chunks | total tok | min | max | mean | over 510 | under 30 |
|---|---|---|---|---|---|---|---|
| `B_train.py` | 78 | 16,932 | 32 | 500 | 217 | 0 | 0 |
| `A_paper.md` | 18 | 3,961 | 48 | 393 | 220 | 0 | 0 |

Real headers, showing that oversized units keep their identity and that the
overlap is genuinely present (1215 then 1212):

```
[B_train.py · class Trainer · def fit · part 1/5 · lines 1189-1215]
[B_train.py · class Trainer · def fit · part 2/5 · lines 1212-1235]
[B_train.py · class QuoraTokenizer · def __init__ · lines 425-431]
[A_paper.md · 4.1 Input representation and tokenization · lines 53-72]
```

Suite at this point: **110 unit tests, 7 smoke, ruff clean.**

