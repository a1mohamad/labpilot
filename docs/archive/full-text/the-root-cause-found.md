# Full text: The root cause, found 2026-08-17 session 10

[Docs home](../../README.md)

## The root cause, found 2026-08-17 session 10

*Three probes, three requests, no source changed. The probe script lives in the
session scratchpad; the three answers are saved in `artifacts/` as
`*_probe-*.md`.*


### The finding, in one line

> **We asked the model one question and graded it on four.**

The prompt defined the job as *"check what A states against what B does."* The
model did that job correctly in all seventeen runs. Everything B does that A
never discusses was, by that definition, **not part of the job**.


### The worked example — the same line, two answers

`B_train.py` sets `VOCAB_SIZE = 20000`, and A says the vocabulary *"is capped at
the 20,000 most frequent tokens."* Under the comparison question the model wrote:

```
A-5 | says: cap vocabulary at 20,000 | B: does it
```

**That answer is correct.** B matches A, so nothing is reported. Under a
different question — *"is this a bad idea even though it works?"* — the same
model, same context, wrote:

```
103,212 unique tokens in the data, cap 20,000
-> 83,212 words (80.62%) become <UNK>, and <UNK> is masked out of attention
```

**One line of code. Two questions. Two correct answers. Only one is useful.**


### The four questions, and what each one alone can find

| Question | Finds | Did the old prompt ask it? |
|---|---|---|
| 1. Does B match A? | the 11 findings, all A-anchored | yes |
| 2. What in B **breaks** on its own? | #17, #18, #12 | badly — `§4` had no method and always answered `NONE` |
| 3. What in B **runs fine and is still bad**? | #14, #9, #6 | **no** |
| 4. What do B's **own numbers** say when subtracted? | #10b | **no** |

Every question returns findings the other three cannot see. We asked one and a
half of them.


### What the three probes measured

All three: `gemini-3.6-flash`, all 78 parts of B, **no side A at all**, same
citation rule, same hint list, same header/closing shape as `CORE`.

| probe | change | finish | result |
|---|---|---|---|
| v1 HIGH | discovery framing | **`MAX_TOKENS`** | void — cut at B-38, §2–§4 never ran |
| v1 MEDIUM | thinking → MEDIUM | `STOP` | **#17 and #18 found** — 0/17 before |
| **v2 MEDIUM** | + §3 non-crash question, + §4 *"read every number block"* | `STOP` | **#14, #10b, #9, #6 found** · 167/171 citations resolve (**98%**) |

**Seven `EXPECTED.md` findings recovered from B alone. Five of them had never
appeared once in seventeen comparison runs.**


### Three candidate causes, all eliminated by measurement

| Candidate | How it died |
|---|---|
| **retrieval / missing context** | the stuffed runs sent all 96 chunks and still missed everything |
| **lost in the middle** | `#17` sits at **B-77, the last chunk, 97% of the prompt**. Missed 17 times, then found — at the same position. `#10b` sits at **B-0, the first chunk**, and was missed too. The predicted U-shape never appeared |
| **the model is too weak / one call has a ceiling** | the **same model**, at **lower** thinking, in **one call**, found the hardest ones once the question changed |

**A position pattern did appear and it was a confound.** The four
noticed-but-unjudged findings sat at 15–47% and the judged ones spread to 97% —
but `P1` sat at 19%, inside the "unjudged" band, and *was* judged. Early parts of
a training script are config and preprocessing, which is simply where quiet
design choices live. **Kind of finding, not position, is the gate.**


### The second failure — noticing without judging

Probe v1 wrote the facts and never escalated them:

```
§3 table:  103,212 unique tokens  |  20,000 cap  |  unknown ratio 0.0049
§3 then:   "do any two of these numbers disagree?"  ->  NONE
```

Two separate causes, both ours:

1. **§2 asked only a crash question** — *"what input would make this behave
   wrongly?"* #14, #15, #16 and #10b break on **no input**. They are invisible to
   a crash question by construction.
2. **§4 read one third of one chunk.** It listed every number from B-0's `DATA`
   and `MODEL` blocks and **none** from its `RUN SUMMARY` block — so the train/val
   F1 pair was never a candidate. Telling it *"read EVERY block of numbers"*
   fixed it in one line.


### The price: discovery framing manufactures bugs

| framing | false positives |
|---|---|
| comparison — match text against text | almost none |
| **discovery — judge code on its own** | **real, and ranked first** |

Both false alarms are **odd-looking but correct** code:

```
DEVICE  = get_device.__func__()      # a @staticmethod called in the class body
EMB_DIR = ROOT_DIR.parent.parent     # unusual, not wrong
```

`P1` was ranked **worst-first, `high` confidence**, claiming *"crashes execution
immediately"*. It does not.

**This file already predicted it**, for the correspondence gate: *"never put
'tell me if they don't correspond' inside the main prompt — the model will find
something, being unhelpful is against its training."* Writing
`§5 PROBLEMS, WORST FIRST` guarantees problems. Some will be invented.

Rule 2 existed to stop this (*general knowledge → "this is unusual", never "this
is wrong"*) and did not fire, because the model claimed *"seen in the text"*. It
did not hallucinate the code; it **misread** it and then escalated.

> **Recall and precision move in opposite directions. Asking "find bugs" buys a
> second obligation: "is this really a bug?"** That is a separate pass, and it is
> a better argument for the Step 2 loop than the one this file used to make.


### `EXPECTED.md` needs an impact column — "11 of 18" was grading noise

Two of the eighteen change the result by nothing:

| # | claim | real size |
|---|---|---|
| 15 | rows dropped when empty after the regex | the run summary says **`empty rows removed 3`** — of 404,290. **0.0007%** |
| 16 | three layer-norm modules built, flags all `False` | ~1,636 of 11,633,737 parameters. **0.01%**, no gradient, no effect |

**Skipping those two is good judgement, not a miss.** Ranked by impact, discovery
framing found **every B-only finding that can move the outcome** and correctly
ignored the two that cannot.

Every coverage number in this file — 10/18, 11/18, the predicted 15–16, the
"ceiling of 11" — treated a 4.1-F1 defect and a 3-row defect as equal. **Add an
impact column before scoring anything again.**


### Thinking burn, HIGH is not better, measured 2026-08-17

Identical prompt, identical model, only `thinkingLevel` changed:

| | visible answer | spent thinking | finish |
|---|---|---|---|
| HIGH | 2,253 | ~29,747 (**93%**) | **`MAX_TOKENS`** |
| **MEDIUM** | **5,655** | ~26,345 | **`STOP`** |

**MEDIUM produced 2.5× more report and a better one.** The user proposed MEDIUM;
this file's author argued for HIGH "to hold one variable" and lost the run.

This retires the note under [thinking presets](../../agent/design.md#thinking-level--a-user-preset-never-a-per-model-switch)
that every measurement ran at HIGH. It also explains `20-42`, `20-45` and `21-24`
— **four runs killed by thinking burn, not by provider failure.**

> **More thinking is not more answer. Past some point it is less answer.**
> `MEDIUM` is the new default for report-sized outputs; `HIGH` must be justified
> by a measurement, not assumed.


### The instruction bugs, found by experiment 2026-08-17

Real defects in `instructions.py`, each with its evidence:

1. **Rule 6 fights `§5`.** Rule 6: *write a line for every id, including ids you
   did not read.* `§5`: *every line that is not "nothing" must become a row.* A
   line reading `not in the text I was given` is neither, so it must become a row
   with nothing to put in it. Run `2026-08-15_00-11` spent its **entire 32,000
   token budget** arguing the deadlock with itself and produced no report:

   ```
   Wait, if we write `B-46 | not in the text I was given` in §3,
   does it have to appear in §5?
   Wait, is this "nothing"?
   Wait, but we haven't read them!
   ```

2. **`§3 WALK SIDE B` never escapes A.** Its own template is
   `does: <something this part decides that A never mentions>` and
   `nothing A does not already mention`. The section meant to find B-only things
   measures B against A in its own wording.

3. **We gave an exit and it was taken.** Rule 3 *"NONE is a correct answer"* plus
   `§4 may be NONE` produced `§4 PROBLEMS IN B ALONE: NONE` in **every** `FULL`
   run.

4. **`says nothing that can be checked` gets spent on A's best parts.** Run
   `20-45`: `A-15 | says nothing that can be checked` (the results table) and
   `A-16 | says nothing that can be checked` (the ablation table carrying −4.1,
   −1.9, −1.4). The cheapest line went to the most valuable content.

5. **A name is not a method.** `FULL §4` says *"problems that need no
   reference"* → `NONE`, every run. `CORE §4` says *"what input would make this
   behave wrongly? follow the value through, step by step"* → found real bugs.
   Same model, same context.

6. **Placement wastes the strongest position.** Measured on the stuffed prompt:

   | block | tokens | position |
   |---|---|---|
   | header — rules, labels, **every section definition** | 2,052 | 0–5% |
   | SIDE A | 4,789 | 5–22% |
   | SIDE B | 21,036 | 22–99% |
   | closing | **156** | **99.4%** |

   `WALK SIDE B` — with the whole hint list — sits at **5.4%**. The last thing the
   model reads before writing is *"count the ids in the list and write that many
   lines."* **It counted lines.** The word "B" does not appear in the closing.


### What the new instructions must ask

`instructions.py` is rebuilt around the four questions, in this order. Probe v2
proves one call can carry all four.

| § | Question | Must say |
|---|---|---|
| walk | what each part **does** | one line per id, positional |
| A | does B match A? | only when A exists; keep the citation rule unchanged |
| **breaks** | what input makes this behave wrongly? | follow the value through, naming every part it passes |
| **smells** | what runs fine and is still bad? | five sub-questions: built and never used · a cap that discards much of the input, *with the share* · removed or changed before use · a name that says one thing while the code does another · would a reviewer call this a bad idea. **"It runs" is not a reason to leave one out** |
| **numbers** | what do the numbers say? | **read every block of numbers, not the first one you meet** · then subtract and divide pairs and show the arithmetic |
| rank | worst first | **by impact on the outcome, not by confidence** |

**Four things to carry over unchanged, because they are measured to work:**
deterministic quoting (`[B-17 "…"]`, 98–99% resolve) · the positional walk as a
*shape* · the evidence-basis wording of rule 2 · `MEDIUM` thinking.

**Three things to fix while rebuilding:** delete the rule-6/`§5` deadlock · move
the *what to look for* text next to the material or repeat it in the closing ·
add a cheap precision pass, because discovery framing ranked a false alarm first.
