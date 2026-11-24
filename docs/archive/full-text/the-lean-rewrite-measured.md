# Full text: The lean rewrite, measured 2026-08-17 session 10

[Docs home](../../README.md)

## The lean rewrite, measured 2026-08-17 session 10

*Everything above diagnosed the problem. This section is what fixed it, and the
headline is uncomfortable: **the fix was deletion.***


### The citation rate was never real, the bug was ours

`resolve()` compared quotes literally. Inside a Markdown table the model escapes
the pipe, so a **correct** quote failed to match:

```
model writes   [B-8 "SCHEDULER_TYPE = \"ReduceLROnPlateau\""]
real line              SCHEDULER_TYPE = "ReduceLROnPlateau"
```

**77% of every "failed" citation was this.** Re-scored with a three-line
`unescape()`, the whole history moves:

| run | was | now |
|---|---|---|
| `full` 20-38 | 33% | **100%** |
| `full` 21-08 | 31% | 91% |
| `report` today | 62% | 91% |
| `00-16` core | 79% | 97% |

**`FULL` was never the "bad citation" template.** It writes more tables, so it
tripped our bug more often. We judged a template on a defect in our own matcher.
True invention is **1-9%**, not 20-37%.

> **The 99% that made us confident came from the single most favourable run.**
> Same error as *11/18* and *"FULL never finishes"*: reading a number without
> asking which cases produce it.


### Instruction bloat suppresses judgment, literature plus our own data

The user proposed this; searching confirmed it.

- **Models interpolate instructions, they do not select them** - *"LLMs execute
  instructions probabilistically ... they interpolate between strategies **in
  proportion to their textual weight**"*
  ([Less Is More, 2604.18897](https://arxiv.org/html/2604.18897v1)).
  **This is why "side A does not exist" failed.** A few dozen tokens cannot
  outweigh thousands. Obedience is not the mechanism.
- **Merging prompts yields the arithmetic mean, not the maximum** (same paper).
  We merged `FULL`+`CORE`+`DISCOVER` into `REPORT` and got exactly that: 11, and
  it *lost* `#17`, which `CORE` found.
- **Collapse begins near 2KB.** Ours were 6.6-12.6KB.
- **Detailed prompts bias toward inventing faults**
  ([2508.12358](https://arxiv.org/html/2508.12358v1)) - that is `DEVICE` and
  `PROJECT_DIM`, both correct code flagged at `high` confidence.
- **Long checklists lower accuracy** - all 75 CWEs in one prompt *reduced*
  detection ([2401.16310](https://arxiv.org/pdf/2401.16310)).

Our own numbers said it first:

```
bare prompt,      0 bytes  ->  10 findings
core,         6,558 bytes  ->  11
report,      12,620 bytes  ->  11
```

**About 12KB of rules bought one finding over no rules at all.**


### What to cut, and what must never be cut

Cutting to 1,997 bytes kept coverage **and** fixed the conclusion, but broke two
things. The split between them is the transferable rule:

| kind | example | cut it? |
|---|---|---|
| judgment guidance | *"look for a cap that discards input"* | **yes**, the model does it better unprompted |
| **format contract** | `[B-17 "exact line"]` | **no**, `resolve()` parses it. One line gave **0% citations** |
| **logical gate** | a `NO` verdict constraining a later section | **no**, a constraint is not advice |

I cut all three together. The contract needs about four lines, spelling out that
an id alone is not a citation.


### Rule 4 was wrong, not mis-scoped

It said *"do not subtract them"* for any pair marked `NO`. But `EXPECTED.md`'s
own required answer says *"the true gap is **wider than 2.5**"*, **which
requires computing 2.5.** The rule forbade the correct answer.

```
banned    "they cannot be compared"             <- refuses to inform
naive     "B is 2.5 behind"                     <- incomplete
correct   "observed 2.5; B is inflated ~1.5 by
           threshold leakage and helped by 10%
           more training data, so the true gap
           is larger"
```

The lean template reached the third **with no rule telling it to**, in all three
passes. Replace the ban with: *when two numbers were produced differently, give
the difference and say which way it is biased.*

> **The fix for an incomplete statement is to complete it, not to ban it.**


### Multi-pass, vary the model not the seed, measured 2026-08-17

`temperature: 0` makes N passes worthless. Gemini returned **byte-identical**
answers. Multi-pass needs sampling, which costs the repeatability rule.

Three passes at `temperature 0.8`, lean `REPORT`, `gemini-3.5-flash`:

```
pass 1   11 findings      pass 2   11      pass 3   13
union    13              <- no lift over the best single pass
```

**The variance is real** - 33 of 47 raw items appeared in only one pass - but the
hard misses are **systematic per model**, not stochastic:

| | `3.5-flash`, 6+ runs | `3.6-flash` |
|---|---|---|
| #12 / #14 / #18 / #10b | **never** | found |
| `SKIP_CONNECTION` / loss-config / CUDA `Event` | found | never |

> **Repeating one model cannot fix that model's blind spot.** Their blind spots
> are disjoint, so one pass each should beat three passes of either. This
> contradicts the langextract result (2 passes about 93%) **on our task**:
> extraction variance is stochastic, judgement blind spots are not.


### Score in three states, and weight by impact

*(Raised by the user. Flat counting hid the real picture twice.)*

| state | meaning |
|---|---|
| **judged** | named as a problem, with its effect |
| **surfaced** | evidence on the page, uncommented. `0.9439` and `0.8226` listed side by side, gap never stated |
| **absent** | not there in any form |

And the 19 are not equal:

| tier | which | note |
|---|---|---|
| **carries the story** | #11, #6, #1, #9, **#10b** | these *are* the causal explanation |
| secondary | #7 #8 #2 #3 #4 #5 #12 #13 #14 #17 #18 | real, smaller |
| **moves nothing** | #15 (3 rows of 404,290), #16 (0.01% of params) | must never reach a report |

Today's union scored this way: **4 judged plus 1 surfaced of the 5 that carry the
story**, 9 of 12 secondary, and 0 of the 2 that move nothing, correctly ignored.
`EXPECTED.md` still needs these two columns before the next score.


### The deleted checklists, archived for Step 2 and not for the prompt

Cut because a long list *lowers* accuracy in one call. **They are still good
thinking, and each becomes one small node prompt at Step 2**, where a node asks
one question and the list is the whole task rather than a footnote.

**What breaks** - what input would make this behave wrongly? Follow the value
through, naming every part it passes.

**What runs fine and is still bad** - is something built, computed or configured
and then never used (a part behind an always-off flag counts) / is a cap so tight
that much of the input is discarded (give the share) / is something removed or
changed before use / does a name, comment, flag or default say one thing while
the code does another / is a result tuned on the same material it is reported on
/ would a reviewer call this a bad idea even though it works.

**What the numbers say** - read *every* block of numbers, not the first one you
meet / subtract and divide pairs and show the arithmetic.

**Kinds** - contradiction, missing-in-B, missing-in-A, unclear-in-A, defect,
**waste** (runs fine, still bad), scope, same-idea (not a difference).
**Boxes** - input, procedure, measurement, environment, reporting.

> **Do not paste these back into a single-call prompt.** That is exactly the
> 12,620-byte version that scored no better than a bare one.


### Prompt design rules, earned 2026-08-17

Transferable beyond LabPilot. Each one cost a real run.

1. **Write the list of what you want to find first, then check the prompt asks
   for each item.** We wanted bugs in B; nothing asked for bugs in B.
2. **One question finds one kind of thing.** Do not expect a matching question to
   find a judgement problem.
3. **Give every question a method, not a name.** See instruction bug 5.
4. **Never give an easy exit to a section whose job is to find things.**
5. **Put the instruction near the material, and never spend the last position on
   bookkeeping.** The end of a prompt is expensive.
6. **Read your own rules against each other before sending one.** Ours
   deadlocked and cost 32,000 tokens.
7. **Grade content, never shape.** 78 lines is not 78 findings.
8. **A demand for findings produces findings.** Budget for false positives
   whenever you ask a model to judge rather than to match.
9. **Delete before you add.** Every fix on 2026-08-17 that worked was a removal;
   every addition made it worse. Cutting 12,620 bytes to 1,997 held coverage and
   fixed the conclusion.
10. **Separate judgment from contract.** Loosen advice all the way to nothing;
    keep the parsed format and the logical gates exact. Cutting the citation
    spec to one line cost 100% of citations.
11. **Do not ban a comparison — require the caveat.** A refusal is not more
    honest than a qualified number.

> **A model does not find what is important. It finds what you asked for.**
> **And the more you tell it, the less of its own judgment you get.**

---


### The original slice 4 plan *(delivered — kept for the reasoning)*

*Written 2026-08-14, at the end of session 5.*

> Turn the bare context into a real comparison prompt.

**Everything below the prompt already works.** Do not touch `ingest/` — the
chunker is permanent and measured. Do not improve `retrieval/select()` — it is
deleted at Step 1, and making it better would *hide* the failure that motivates
Step 1.

**The four things slice 4 must produce**, in the order they matter:

1. **Instructions.** What the tool is, the five things every report must contain
   (bugs · design differences · missing details · the causal story · the next
   experiment), and the output shape.
2. **A citation mechanism that actually works** — see failure 1 above. This is
   not a sentence in the prompt; it is a design decision about how chunks are
   rendered.
3. **A rule about comparing numbers** — see failure 2 above. Check that two
   numbers were measured the same way before subtracting them.
4. **Real `max_tokens` values**, and the `thinking` field on `GeminiProvider`
   that [Thinking models](../../llm/failure-rules-and-limits.md#thinking-models--the-count-is-at-least-four-of-seven)
   defers to this slice. Get the exact REST field name from `<> Get code` in AI
   Studio, not from memory.

**Measure it the same way.** Re-run the smoke test, score the answer against
`EXPECTED.md`, and compare with the 5/10 baseline above. **The baseline is the
point** — without it there is no way to tell whether the prompt helped.


### Where to pick up — slice 3, dumb retrieval *(closed — kept for the reasoning)*

*Written 2026-08-12, at the end of session 3.*

> Read one hardcoded paper + code pair from `data/samples/`, cut it into pieces,
> pick some, and hand them to `LLMClient`.

**"Dumb" is the point.** No embeddings, no pgvector, no scoring — those are
Step 1. Slice 3 exists to prove the *shape* of the pipeline
(files → text → chunks → selection → prompt) before any part of it becomes
clever. This is also the first piece of the RAG gap, so it gets the full
teaching treatment described under
[The four gaps](../../rules/teaching-and-communication.md#the-four-gaps-are-the-whole-point--teach-them-hardest-of-all).

**But "dumb" applies to exactly one box.** *(Clarified 2026-08-13.)* Chunking is
**real and permanent** — the chunker written here is the one Step 1 keeps, and a
chunking mistake cannot be repaired by any later stage. Only **selection** is
throwaway: a hardcoded rule now, replaced by cosine similarity plus reranking at
Step 1. Build the chunker to the specification in
[Chunking](../../retrieval/chunking.md#chunking--decided-2026-08-13-built-in-slice-3), including the full
metadata field set, and treat the selector as scaffolding.

Slice 3 is also where you will **see** the problem that motivates Step 1: the
dumb selector returns the wrong chunks, and the model answers badly because it
was handed the wrong two paragraphs. That contrast is the point of building it.

**Two RAG lessons were taught before this slice** (session 4): *what RAG is and
why it exists*, and *chunking*. Embeddings, cosine similarity, vector databases
and reranking are taught at Step 1, each one immediately before it is built.

**~~One thing blocks it: `data/samples/` is empty.~~ UNBLOCKED 2026-08-14 —
see [The sample pair](../../reference/sample-pair.md#the-sample-pair--quora_siamese-built-2026-08-14).**

**Loose ends carried into the next session:**

- ~~`CLOUDFLARE_API_KEY` and `CLOUDFLARE_ACCOUNT_ID` are missing as GitHub
  repository secrets.~~ **Added 2026-08-14 — all seven secrets are present and
  `smoke.yaml` maps them correctly. Tier 7 should pass on the next run.**
- The weekly smoke run should print each raw response body **once**, to settle
  which of tiers 2, 5 and 6 are thinking models — see
  [Thinking models](../../llm/failure-rules-and-limits.md#thinking-models--the-count-is-at-least-four-of-seven).


### The sample pair — `quora_siamese`, built 2026-08-14

`data/samples/quora_siamese/` holds three files. **The pair is the measuring
instrument for the whole of slice 3** — without a known answer there is no way
to tell a working chunker from a broken one.

| File | ~tokens | What it is |
|---|---|---|
| `A_paper.md` | 3,900 | side A, the reference. **Fictional**, written for this fixture |
| `B_train.py` | 16,500 | side B, the implementation. **Real code**, flattened from `research-notebooks/Quora Questions Pairs/research/` |
| `EXPECTED.md` | — | the answer key. **Never ingested** |

**Side B is real and side A is not, and that asymmetry is deliberate.** The code
is the user's own — `02-train.ipynb` plus `model_architecture.py` merged into one
file, values, comments and flaws untouched — and its `DATA` / `MODEL` /
`RUN SUMMARY` docstring is transcribed from the notebook's stored outputs (MLflow
run `LSTM_attention-MultiHead-Bahdanau-v10`). The paper has to be invented,
because a real paper never lines up with a reimplementation cleanly enough to
place claims that *match*, claims that *contradict*, and claims the code never
addresses at all.

**Total ≈ 20,400 tokens against `INPUT_BUDGET` of 20,000.** Stuffing is
impossible by construction, so retrieval must work. That was the sizing target,
not an accident.

**18 divergences, in the three kinds the similarity matrix reads:**

| Kind | Count | The one that matters |
|---|---|---|
| stated and **wrong** (rows, `verify`) | 6 | the paper pools `Σ αᵢhᵢ` over hidden states; `B_train.py:601-603` pools the **projected** features, and the code's own comment says so |
| stated and **absent** (rows, `verify`) | 5 | `pos_class_weight()` is defined at `:561` and **never called** |
| **unstated** but present (columns, `find_missing`) | 7 | stopword masking — `_build_stop_mask` at `:450` and `_encode` at `:678` |

Plus one latent bug findable from a single artifact: a question of only
stopwords masks to all zeros, so softmax over a constant returns uniform weights
and the sentence encodes to the zero vector.

**Three properties worth preserving if the pair is ever replaced:**

1. **The scattered fact.** The stopword finding needs two chunks from two
   classes, ~230 lines apart. One retrieved chunk cannot explain it.
2. **Honest distractors.** `TrainConfig` configures four LR schedulers and only
   `ReduceLROnPlateau` is live, so any "learning rate schedule" query pulls back
   dead constants. Nothing was planted — the code really is like that.
3. **The two numbers are not comparable.** Paper 0.851 F1 on a clean test split;
   code 0.8262 on a validation split whose threshold was tuned on itself. A
   naive system subtracts them and reports "2.5 points behind". **The correct
   answer refuses the subtraction**, and the per-epoch threshold sequence
   (0.4358 → 0.3970 → 0.4825 → 0.3893 → 0.4631 → 0.5787) is the evidence.

**The arithmetic deliberately does not close.** The four defects predict ≈ −8 F1
if the paper's ablations composed additively; the observed gap is ≈ 2.5. A good
report offers the three honest readings — ablations overlap, the code's number
is inflated, the code has advantages the paper lacks — instead of asserting one.

**Chunker coverage.** The pair exercises every path on purpose: 3 markdown
sections under the ~30-token minimum (**merge**), `§4.3` at ~656 tokens
(**second-pass split** with repeated header), 11 AST units over the 510 cap,
largest `class Trainer` (lines 920-1317) at ~5,300 tokens, and `Trainer.fit` (lines 1189-1317) as the training loop
that must stay whole.

**`data/samples/` is excluded from ruff and from pre-commit.** The fixture is
data, not source: `ruff check .` would fail CI on flaws that are the point, and
`ruff-format` would move the exact lines `EXPECTED.md` cites. The exclusion is
in both `ruff.toml` and `.pre-commit-config.yaml` and the two must stay in step.
**It does not affect ingest** — the chunker still reads these files normally.

**A process lesson from building it.** The first version invented the run
summary, because the notebook dump extracted cell *source* and skipped cell
*outputs*. The real numbers were in the file the whole time. **When a notebook is
the source of truth, read its outputs, not only its code** — stored outputs are
the only record of what actually happened.

