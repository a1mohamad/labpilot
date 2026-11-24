# Prompt experiments and prompt design rules

[Docs home](../README.md)

### Where to pick up — slice 4's coverage problem

*Written 2026-08-14, session 7; replaced the slice 4 plan below, whose four items were all delivered. Its line "the four prompt fixes are written but never scored" was overtaken:
**they were scored 2026-08-17 and did not work** (next section).*

### The prompt fixes were measured, and they failed — 2026-08-17

Both runs stuffed (96/96), both `gemini-3.6-flash`, both `STOP`; only the prompt differed.

| | baseline `21-27` | post-fix `00-16` |
|---|---|---|
| findings | **11 / 18** | **11 / 18** |
| predicted | — | 15–16 |
| citations resolve | 73/74 (99%) | 118/148 (80%) |

The prediction said "treat 14 or more as the fix working, and 11 as the diagnosis being wrong": **it is 11, and a *different* 11** (it gained #9, the threshold tuned on the reported
split, and **lost #5**, the unfreeze off-by-one — "unfreeze" does not appear anywhere in the post-fix answer, not even in the 78-line walk).

~~"The walks ran ... Enumeration was never the bottleneck. Judgement is."~~ > **CORRECTED 2026-08-17, session 10: both sentences were wrong. The walks were printed, not executed
— and we never read them.** This file's own instruction was "count the walk lines; if the walk has 40 lines, rule 6 was ignored" — we counted and stopped. Reading them shows three
empty shapes: `21-24 B-45 / B-46 / B-47 ...` (bare ids, no verdict) · `23-50 B-38 | Decides MLflow parameter logging helpers, which A never mentions` · `00-16 B-18 | nothing A
does not already mention` (**B-18 does hold a finding**). **A shape check is not a content check** — grading the shape is how a failed fix passed for three days.

**Two new problems the fixes created:** (1) **it merged findings** (`D7` = weight decay *and* clip norm; `D8` = no test split *and* threshold re-tuned: the failure
[claim extraction](../retrieval/design.md#claim-extraction--how-side-a-becomes-queries) names, "merged, a partial match reads as a match and two real mismatches disappear"; the count held only because they
were unpacked by hand); (2) **citation resolution fell 99% → 80%** (more citations written, 74 → 148, a larger share wrong).

**The scoring lesson, which cost an hour:** a regex screen said the baseline lacked findings #5 and #6; it had both, in *words* ("B unfreezes at epoch 4", not `UNFREEZE_EPOCH`).
**Pattern matching is a screen, never a score** ("a miss you have not looked up is evidence about your scoring, not the model" — and it happened again).

**What this settled:** the remaining seven misses all require reasoning about **B on its own terms** (`find_bugs`, `find_missing`); the measured split stands: retrieval costs ≈ 2
findings, the single call costs ≈ 7. ~~"So Step 2 is a requirement ... the numbers now say so. Stop tuning the prompt."~~ > **CORRECTED 2026-08-17, session 10.** The split is
real; the conclusion was not: it rested on **one** clean run (every other post-fix run was truncated or litigating rule conflicts), and a single call **did** find those seven once
the question changed — **the 7 belonged to the *question*, not to the *call*.** The explanation moved twice, each time right after a failure (session 7 "no prompt fixes the seven,
it is Step 2" → retracted "the prompt can, predict 15-16" → session 9 "the prompt cannot, Step 2 is a requirement"): the shape this file warns the *model* about in the §9 rule,
bending the reading so the story closes. **When a conclusion moves to protect a plan, re-read the artifacts before writing it down.**

**Two things that changed under the measurement:** tier 1 had become `gemini-3.7-flash` while the 11/18 baseline was set by 3.6, so a straight comparison changes the prompt AND the
model at once — **pin the model** (the like-for-like run `2026-08-15_00-16_core-stuffed_gemini-3.6-flash.md` was already paid for in `artifacts/`). The miss list is not random:
every miss is something B does that A never mentions, or needs reasoning over B's own numbers. Do not touch `ingest/` or improve `select()`; measure **stuffed** so retrieval is not
a variable.

---

## The root cause, found 2026-08-17 session 10

*Three probes, three requests, no source changed; the answers are saved in `artifacts/` as `*_probe-*.md`.*

> **We asked the model one question and graded it on four.** The prompt defined the job as "check what A states against what B does"; the model did that correctly in all
> seventeen runs, and everything B does that A never discusses was, by that definition, **not part of the job**.

**The worked example, the same line, two answers:** `B_train.py` sets `VOCAB_SIZE = 20000`, A says the vocabulary "is capped at the 20,000 most frequent tokens". Under the comparison
question the model wrote `A-5 | says: cap vocabulary at 20,000 | B: does it` (correct: B matches A, nothing to report). Under "is this a bad idea even though it works?" the same
model and context wrote: *103,212 unique tokens in the data, cap 20,000 → 83,212 words (80.62%) become `<UNK>`, and `<UNK>` is masked out of attention*. **One line of code, two
questions, two correct answers; only one is useful.**

### The four questions, and what each one alone can find

(1) Does B match A? → the 11 findings, all A-anchored (asked). (2) What in B **breaks** on its own? → #17, #18, #12 (asked badly: `§4` had no method and always answered `NONE`).
(3) What in B **runs fine and is still bad**? → #14, #9, #6 (**not asked**). (4) What do B's **own numbers** say when subtracted? → #10b (**not asked**). Each returns findings the
other three cannot see; we asked one and a half.

### What the three probes measured

All `gemini-3.6-flash`, all 78 parts of B, **no side A at all**, same citation rule and hint list. v1 HIGH (discovery framing): `MAX_TOKENS`, void (cut at B-38, §2-§4 never ran).
v1 MEDIUM: `STOP`, **#17 and #18 found** (0/17 before). **v2 MEDIUM** (+ §3 non-crash question, + §4 "read every number block"): `STOP`, **#14, #10b, #9, #6 found**, 167/171
citations resolve (**98%**). **Seven `EXPECTED.md` findings recovered from B alone, five of which had never appeared once in seventeen comparison runs.**

### Three candidate causes, all eliminated by measurement

**Retrieval / missing context** (stuffed runs sent all 96 chunks and still missed everything). **Lost in the middle** (`#17` sits at **B-77, the last chunk, 97% of the prompt**:
missed 17 times then found at the same position; `#10b` sits at **B-0, the first chunk**, and was missed too; the predicted U-shape never appeared). **The model is too weak / one
call has a ceiling** (the same model at **lower** thinking, in **one call**, found the hardest ones once the question changed). A position pattern did appear and was a confound
(the noticed-but-unjudged findings sat at 15-47%, but `P1` at 19% *was* judged; early parts of a training script are config and preprocessing, where quiet design choices live).
**Kind of finding, not position, is the gate.**

### The second failure — noticing without judging

Probe v1 wrote facts and never escalated them (§3 table: 103,212 unique tokens | 20,000 cap | unknown ratio 0.0049; then "do any two of these numbers disagree?" → `NONE`). Two
causes, both ours: (1) **§2 asked only a crash question** — #14, #15, #16 and #10b break on **no input**, invisible to a crash question by construction; (2) **§4 read one third of one
chunk** (every number from B-0's `DATA` and `MODEL` blocks and **none** from its `RUN SUMMARY`, so the train/val F1 pair was never a candidate); "read EVERY block of numbers" fixed
it in one line.

### The price: discovery framing manufactures bugs

Comparison framing (match text against text): almost no false positives. **Discovery framing: real, and ranked first.** Both false alarms were odd-looking but correct code
(`DEVICE = get_device.__func__()`, a `@staticmethod` called in the class body; `EMB_DIR = ROOT_DIR.parent.parent`); `P1` was ranked worst-first at `high` confidence claiming "crashes
execution immediately". This file predicted it for the correspondence gate ("never put 'tell me if they don't correspond' inside the main prompt — the model will find something");
writing `§5 PROBLEMS, WORST FIRST` guarantees problems. Rule 2 (*general knowledge → "this is unusual", never "this is wrong"*) did not fire because the model claimed "seen in the
text": it **misread** the code and then escalated. > **Recall and precision move in opposite directions; asking "find bugs" buys a second obligation, "is this really a bug?" —
a separate pass, and a better argument for the Step 2 loop than the one this file used to make.**

### `EXPECTED.md` needs an impact column — "11 of 18" was grading noise

Two of the eighteen change the result by nothing: **#15** (rows dropped when empty after the regex: `empty rows removed 3` of 404,290, **0.0007%**) and **#16** (three layer-norm modules
built with flags all `False`: ~1,636 of 11,633,737 parameters, **0.01%**, no gradient). Skipping those is good judgement, not a miss; ranked by impact, discovery framing found
**every B-only finding that can move the outcome**. Every coverage number (10/18, 11/18, the predicted 15-16, the "ceiling of 11") treated a 4.1-F1 defect and a 3-row defect as
equal. **Add an impact column before scoring anything again.**

### Thinking burn, HIGH is not better, measured 2026-08-17

Identical prompt and model, only `thinkingLevel` changed: **HIGH** → visible answer 2,253, spent thinking ~29,747 (**93%**), `MAX_TOKENS`; **MEDIUM** → visible **5,655**, thinking
~26,345, `STOP`. **MEDIUM produced 2.5× more report and a better one** (the user proposed MEDIUM; this file's author argued HIGH "to hold one variable" and lost the run). It
retires the note under [thinking presets](../agent/design.md#thinking-level--a-user-preset-never-a-per-model-switch) that every measurement ran at HIGH, and explains `20-42`, `20-45` and `21-24`
— **four runs killed by thinking burn, not provider failure.** > **More thinking is not more answer; past some point it is less.** `MEDIUM` is the default for report-sized outputs;
`HIGH` must be justified by a measurement.

### The instruction bugs, found by experiment 2026-08-17

1. **Rule 6 fights `§5`:** rule 6 "write a line for every id, including ids you did not read", `§5` "every line that is not 'nothing' must become a row"; run `2026-08-15_00-11` spent
   its **entire 32,000-token budget** arguing the deadlock with itself and produced no report ("Wait, if we write `B-46 | not in the text I was given` in §3, does it have to appear
   in §5? ... is this 'nothing'?").
2. **`§3 WALK SIDE B` never escapes A:** its template is `does: <something this part decides that A never mentions>` / `nothing A does not already mention`, measuring B against A.
3. **We gave an exit and it was taken:** rule 3 "NONE is a correct answer" plus `§4 may be NONE` produced `§4 PROBLEMS IN B ALONE: NONE` in **every** `FULL` run.
4. **`says nothing that can be checked` gets spent on A's best parts** (run `20-45`: `A-15` the results table and `A-16` the ablation table carrying −4.1, −1.9, −1.4).
5. **A name is not a method:** `FULL §4` "problems that need no reference" → `NONE` every run; `CORE §4` "what input would make this behave wrongly? follow the value through,
   step by step" → found real bugs. Same model, same context.
6. **Placement wastes the strongest position.** Stuffed prompt: header (rules, labels, every section definition) 2,052 tokens at 0-5% · SIDE A 4,789 at 5-22% · SIDE B 21,036 at
   22-99% · closing **156 at 99.4%**. `WALK SIDE B` with the whole hint list sits at **5.4%**; the last thing read before writing is "count the ids in the list and write that many
   lines" — **it counted lines**; the word "B" does not appear in the closing.

### What the new instructions must ask

Rebuilt around the four questions (probe v2 proves one call carries all four): **walk** (what each part *does*, one line per id, positional) · **A** (does B match A, only when A
exists; citation rule unchanged) · **breaks** (what input makes this behave wrongly; follow the value through, naming every part) · **smells** (what runs fine and is still bad: built
and never used · a cap that discards much of the input, *with the share* · removed or changed before use · a name that says one thing while the code does another · would a
reviewer call this a bad idea; **"it runs" is not a reason to leave one out**) · **numbers** (read every block of numbers, not the first one; subtract and divide pairs, show the
arithmetic) · **rank** (worst first, **by impact on the outcome, not by confidence**). Carry over unchanged because measured: deterministic quoting `[B-17 "…"]` (98-99% resolve),
the positional walk as a *shape*, the evidence-basis wording of rule 2, `MEDIUM` thinking. Fix: the rule-6/`§5` deadlock; move the *what to look for* text next to the material or
repeat it in the closing; a cheap precision pass.

## The lean rewrite, measured 2026-08-17 session 10

*Everything above diagnosed the problem; this is what fixed it, and the headline is uncomfortable: **the fix was deletion.***

### The citation rate was never real, the bug was ours

`resolve()` compared quotes literally; inside a Markdown table the model escapes the pipe, so a **correct** quote failed (`[B-8 "SCHEDULER_TYPE = \"ReduceLROnPlateau\""]` vs the real
line `SCHEDULER_TYPE = "ReduceLROnPlateau"`). **77% of every "failed" citation was this.** Re-scored with a three-line `unescape()`: `full` 20-38 33% → **100%** · `full` 21-08 31% → 91%
· `report` today 62% → 91% · `00-16` core 79% → 97%. **`FULL` was never the "bad citation" template** (it writes more tables, tripping our bug more often); we judged a template on a
defect in our own matcher. True invention is **1-9%**, not 20-37%. > **The 99% that made us confident came from the single most favourable run** — the same error as *11/18* and
*"FULL never finishes"*: reading a number without asking which cases produce it.

### Instruction bloat suppresses judgment, literature plus our own data

*(The user proposed this; searching confirmed it.)* **Models interpolate instructions, they do not select them** ("in proportion to their textual weight", [Less Is More,
2604.18897](https://arxiv.org/html/2604.18897v1)) — **why "side A does not exist" failed**: a few dozen tokens cannot outweigh thousands. **Merging prompts yields the arithmetic mean,
not the maximum** (same paper): `FULL`+`CORE`+`DISCOVER` merged into `REPORT` gave 11 and *lost* `#17`, which `CORE` found. **Collapse begins near 2KB** (ours were 6.6-12.6KB).
**Detailed prompts bias toward inventing faults** ([2508.12358](https://arxiv.org/html/2508.12358v1); `DEVICE` and `PROJECT_DIM`, both correct, flagged at `high`). **Long checklists
lower accuracy** (all 75 CWEs in one prompt reduced detection, [2401.16310](https://arxiv.org/pdf/2401.16310)). Our own numbers said it first: bare prompt (0 bytes) 10 findings ·
core (6,558) 11 · report (12,620) 11 — **about 12KB of rules bought one finding over no rules at all.**

### What to cut, and what must never be cut

Cutting to 1,997 bytes kept coverage and fixed the conclusion but broke two things; the transferable rule: **judgment guidance** ("look for a cap that discards input") **cut it**, the
model does it better unprompted · **format contract** (`[B-17 "exact line"]`) **never cut it**, `resolve()` parses it, one line gave **0% citations** · **logical gate** (a `NO`
verdict constraining a later section) **never cut it**, a constraint is not advice. I cut all three together; the contract needs about four lines, spelling out that an id alone is
not a citation.

### Rule 4 was wrong, not mis-scoped

It said "do not subtract them" for any pair marked `NO`, but `EXPECTED.md`'s own required answer says "the true gap is **wider than 2.5**", **which requires computing 2.5.** Banned
("they cannot be compared": refuses to inform) / naive ("B is 2.5 behind": incomplete) / correct ("observed 2.5; B is inflated ~1.5 by threshold leakage and helped by 10% more
training data, so the true gap is larger"). The lean template reached the third with no rule telling it to, in all three passes. Replace the ban with: *when two numbers were
produced differently, give the difference and say which way it is biased.* > **The fix for an incomplete statement is to complete it, not to ban it.**

### Multi-pass, vary the model not the seed, measured 2026-08-17

`temperature: 0` makes N passes worthless (Gemini returned **byte-identical** answers); multi-pass needs sampling, which costs the repeatability rule. Three passes at
`temperature 0.8`, lean `REPORT`, `gemini-3.5-flash`: 11 / 11 / 13, union 13 (no lift over the best single pass). The variance is real (33 of 47 raw items appeared in only one pass)
but the hard misses are **systematic per model**: `3.5-flash` (6+ runs) **never** finds #12 / #14 / #18 / #10b and finds `SKIP_CONNECTION` / loss-config / CUDA `Event`; `3.6-flash`
finds the first four and never the second three. > **Repeating one model cannot fix that model's blind spot.** Their blind spots are disjoint, so one pass each should beat three
passes of either — contradicting the langextract result (2 passes ≈ 93%) **on our task**: extraction variance is stochastic, judgement blind spots are not.

### Score in three states, and weight by impact

*(Raised by the user; flat counting hid the real picture twice.)* **judged** (named as a problem, with its effect) · **surfaced** (evidence on the page, uncommented: `0.9439` and
`0.8226` side by side, gap never stated) · **absent**. And the 19 are not equal: **carries the story** #11, #6, #1, #9, **#10b** (these *are* the causal explanation) · secondary
#7 #8 #2 #3 #4 #5 #12 #13 #14 #17 #18 · **moves nothing** #15, #16 (must never reach a report). Today's union: **4 judged plus 1 surfaced of the 5 that carry the story**, 9 of 12
secondary, 0 of the 2 that move nothing (correctly ignored). `EXPECTED.md` still needs these two columns before the next score.

### The deleted checklists, archived for Step 2 and not for the prompt

Cut because a long list *lowers* accuracy in one call; **each becomes one small node prompt at Step 2** (a node asks one question and the list is the whole task). **What breaks** —
what input would make this behave wrongly? follow the value through, naming every part it passes. **What runs fine and is still bad** — built, computed or configured and then never
used (a part behind an always-off flag counts) / a cap so tight that much of the input is discarded (give the share) / removed or changed before use / a name, comment, flag or
default saying one thing while the code does another / a result tuned on the same material it is reported on / would a reviewer call it a bad idea even though it works. **What the
numbers say** — read *every* block of numbers; subtract and divide pairs and show the arithmetic. **Kinds** — contradiction, missing-in-B, missing-in-A, unclear-in-A, defect,
**waste**, scope, same-idea (not a difference). **Boxes** — input, procedure, measurement, environment, reporting. > **Do not paste these back into a single-call prompt** (that is
the 12,620-byte version that scored no better than a bare one).

### Prompt design rules, earned 2026-08-17

Transferable beyond LabPilot; each cost a real run.
1. **Write the list of what you want to find first, then check the prompt asks for each item** (we wanted bugs in B; nothing asked for bugs in B).
2. **One question finds one kind of thing.**
3. **Give every question a method, not a name** (instruction bug 5).
4. **Never give an easy exit to a section whose job is to find things.**
5. **Put the instruction near the material, and never spend the last position on bookkeeping.**
6. **Read your own rules against each other before sending one** (ours deadlocked and cost 32,000 tokens).
7. **Grade content, never shape.** 78 lines is not 78 findings.
8. **A demand for findings produces findings.** Budget for false positives whenever you ask a model to judge rather than match.
9. **Delete before you add.** Every fix that worked on 2026-08-17 was a removal; every addition made it worse (12,620 → 1,997 bytes held coverage and fixed the conclusion).
10. **Separate judgment from contract.** Loosen advice to nothing; keep the parsed format and the logical gates exact (cutting the citation spec to one line cost 100% of citations).
11. **Do not ban a comparison — require the caveat.** A refusal is not more honest than a qualified number.

> **A model does not find what is important. It finds what you asked for. And the more you tell it, the less of its own judgment you get.**

---

### The original slice 4 plan *(delivered — kept for the reasoning)*

*Written 2026-08-14.* Turn the bare context into a real comparison prompt; everything below the prompt already worked (do not touch `ingest/`, do not improve `select()` — improving
the throwaway selector would *hide* the failure that motivates Step 1). It had to produce: (1) **instructions** (what the tool is, the five things every report contains — bugs ·
design differences · missing details · the causal story · the next experiment — and the output shape), (2) **a citation mechanism that actually works** (a design decision about how
chunks are rendered, not a sentence), (3) **a rule about comparing numbers** (check two numbers were measured the same way before subtracting), (4) **real `max_tokens` values** and
the `thinking` field on `GeminiProvider` ([Thinking models](../llm/failure-rules-and-limits.md#thinking-models--the-count-is-at-least-four-of-seven); get the REST field name from `<> Get code` in AI Studio). Measure
the same way (smoke test, score against `EXPECTED.md`, compare with the 5/10 baseline: the baseline is the point).

### Where to pick up — slice 3, dumb retrieval *(closed — kept for the reasoning)*

*Written 2026-08-12.* Read one hardcoded paper + code pair from `data/samples/`, cut it into pieces, pick some, hand them to `LLMClient`. **"Dumb" applies to exactly one box**
*(clarified 2026-08-13)*: chunking is **real and permanent** (a chunking mistake cannot be repaired by any later stage; build it to the [Chunking](../retrieval/chunking.md#chunking--decided-2026-08-13-built-in-slice-3)
spec with the full metadata field set), only **selection** is throwaway scaffolding, and it is where you **see** the problem that motivates Step 1 (the wrong two paragraphs →
a bad answer). Two RAG lessons preceded it (what RAG is; chunking); embeddings, cosine, vector databases and reranking were taught at Step 1, each just before it was built.
Unblocked 2026-08-14 by [the sample pair](../reference/sample-pair.md#the-sample-pair--quora_siamese-built-2026-08-14). Loose ends then: the Cloudflare secrets (added 2026-08-14; all seven repository
secrets present) and printing each raw response body once on the weekly smoke run to settle which tiers are thinking models.
