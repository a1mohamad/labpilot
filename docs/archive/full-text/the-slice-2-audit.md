# Full text: The slice 2 audit — 2026-08-28

[Docs home](../../README.md)

## The slice 2 audit — 2026-08-28

*Run at the user's request, asking the same question as the
[2026-08-17 audit](../../step0/slice-5-and-the-api.md#the-system-wide-audit--2026-08-17): **which real failure is
still unprotected?** Three findings, and measurement killed the second one.*


### 1. A test whose name promised more than it checked

```python
def test_no_chunk_exceeds_the_hard_cap(...):
    assert estimate_tokens(chunk.text) <= MAX_CHUNK_TOKENS
```

**What is sent to every embedder and reranker is `chunk.embed_text` — text plus
header.** Measured on a real corpus:

| | |
|---|---|
| max `chunk.text` | 497 |
| **max `chunk.embed_text`** | **519** (`labpilot/` only) · **544** (whole repo) |
| over the 510 cap | 2 of 232 · **43 of 1,094** |

So the test was green while the cap was broken for the only string that matters
— the same shape as `test_the_documented_failures_are_the_ones_the_endpoint_can_raise`
in the last audit. **A test named after an invariant must check that invariant,
not a cousin of it.**

Fixed two ways, neither of which hides the defect:

- renamed to `test_no_chunk_text_exceeds_the_hard_cap` — an honest name
- added `test_no_chunk_exceeds_the_hard_cap_once_its_header_is_added`, marked
  **`xfail(strict=True)`**. It fails today. **When slice 3 moves the cap onto the
  string we actually send, it XPASSes and the suite goes red**, forcing someone
  to delete the marker. Verified by mutation: making `embed_text` drop the header
  turns it into `[XPASS(strict)] 1 failed`.

> `xfail(strict=True)` is how a **known bug we own** stays visible.
> `strict=False` is for things outside our control — a dead provider, a blocked
> region.


### 2. The batch-budget claim — flagged, then killed by measurement

`test_a_full_batch_of_capped_chunks_fits_the_tightest_token_budget` reasons from
`MAX_BATCH_SIZE × MAX_CHUNK_TOKENS ≤ TIGHTEST_TOKENS_PER_MINUTE`, and finding 1
means that bound is not actually held. It looked like a second defect. It is not:

```
claimed  96 x 510 = 48,960 <= 50,000
real worst batch of 96 = 27,310    ok
```

Real chunks average **229** tokens, nowhere near the 510 bound. **The derivation
is formally void and practically safe**, so the test stays as it is. A
replacement measuring real chunks was written and then **deleted**: a 1.8×
margin makes it a number, not a guard.


### 3. Nothing checked that our chunks fit the embedders we ship

`BGE Base EN v1.5` declares `max_input_tokens=512`. An embedder whose limit sits
below `MAX_CHUNK_TOKENS` can never embed this corpus at all — `_check_texts`
would refuse every call, loudly and uselessly.

`test_every_embedder_can_take_a_chunk_at_our_cap` now parametrizes over
`MIGRATION` and fails the build instead. Mutation-verified by lowering BGE to
256. **This is the downstream consequence of finding 1, caught at build time
rather than at runtime.**


### Measured while auditing, and it corrects this file

**Streaming saves 2×, not the 73MB this file implies.**

```
4,108 chunks in the working tree
streamed     : 4.7 MB peak
materialised : 9.9 MB peak
```

The 73MB figure was about **vectors**, not chunks, so the rule is right and its
payoff is deferred to slice 4. Recorded so nobody re-derives it — and so the
streaming rule is not quietly over-sold.


### The three defects, and how each was closed — 2026-08-28

*Found by the audit, fixed the same day at the user's request. All three
mutation-tested: removing each guard breaks exactly one test.*

**1. `os.walk` silently swallowed unreadable directories.** ✅ **FIXED.** Its
default is `onerror=None`, so on Linux a permission-denied subdirectory vanished
with no entry in `source.skipped` — breaking this project's own *"nothing may be
dropped silently"* rule. `walk` now passes an `onerror` callback that records
`unreadable directory`.

> **A default that ignores errors is a silent-drop waiting to happen.** Read the
> default of every traversal API you use; `os.walk` never told us.
**2. One unreadable file aborted the whole ingest.** ✅ **FIXED**, in both
places it could happen. `chunk_source` caught only `UnicodeDecodeError`, and
`_reason_to_skip` could raise from `stat()` if a file vanished between listing
and reading — likely on a live working tree with an editor or an antivirus
holding a file. Both now catch `OSError` and count `unreadable file`.

The fix also removed a real inefficiency: `_reason_to_skip` called `stat()` and
then `walk` called it **again**. It is now `_inspect`, returning
`(reason, size)` from **one** `stat`, using `S_ISREG` instead of a second
`is_file()` syscall.

**`Source.skip(reason)` was added in the same pass**, because two layers were
each hand-writing `skipped[reason] = skipped.get(reason, 0) + 1`. Counting
belongs to the object that owns the count.
**3. `MAX_ARCHIVE_BYTES` (50MB) can never arrive through the API**, whose
`MAX_REQUEST_BODY_BYTES` is about 2MB. ⏸ **Pinned, not fixed** — and that is the
right answer. "Fixing" it means choosing whether the archive limit falls or the
upload limit rises, and that is a policy for a feature that does not exist yet;
inventing a number now would be a guess dressed as a decision.

So the **invariant** is written down instead, as
`test_an_archive_we_accept_must_be_able_to_reach_us` marked
`xfail(strict=True)`. Slice 7 cannot wire an archive into the endpoint without
the suite turning red.

> **A limit the system can never reach is a lie.** When you cannot yet choose
> the number, pin the relationship the numbers must satisfy.

---


### Where to pick up — slice 4's coverage problem

*Written 2026-08-14, session 7. **This replaces the slice 4 plan below**, which
is kept because all four of its items were delivered.*

> ~~The four prompt fixes are written but never scored.~~
> **SCORED 2026-08-17. They did not work.** Read the next section instead.


### The prompt fixes were measured, and they failed — 2026-08-17

Both runs stuffed (96/96 chunks), both `gemini-3.6-flash`, both `STOP`. Only the
prompt differed.

| | baseline `21-27` | post-fix `00-16` |
|---|---|---|
| findings | **11 / 18** | **11 / 18** |
| predicted | — | 15–16 |
| citations resolve | 73/74 (99%) | 118/148 (80%) |

The prediction said *"treat anything at or above 14 as the fix working, and 11 as
the diagnosis being wrong."* **It is 11.**

**And it is a *different* 11.** It gained #9 (threshold tuned on the reported
split) and **lost #5** (the unfreeze off-by-one) — the word "unfreeze" does not
appear anywhere in the post-fix answer, not even in the 78-line walk.

~~**The walks ran.** 18 A-lines and 78 B-lines, complete, exactly as rule 6
demanded. The fix was executed and produced nothing.~~

~~**Enumeration was never the bottleneck. Judgement is.**~~

> **CORRECTED 2026-08-17, session 10. Both sentences above are wrong.**
> **The walks were printed, not executed — and we never read them.**
>
> This file's own instruction was: *"Count the walk lines. If the walk has 40
> lines, rule 6 was ignored and the fix did not actually run — that is a
> different failure from the fix not working."* We counted. We stopped there.
> Reading the lines shows three different empty shapes:
>
> ```
> 21-24  B-45 / B-46 / B-47 ...        bare ids, no verdict at all
> 23-50  B-38 | Decides MLflow parameter logging helpers, which A never mentions
> 00-16  B-18 | nothing A does not already mention      ← B-18 does hold a finding
> ```
>
> The count was right and the content was empty. **A shape check is not a
> content check** — grading the shape is how a failed fix passed for three days.

**Two new problems the fixes created:**

1. **It merged findings.** `D7` = weight decay *and* clip norm; `D8` = no test
   split *and* threshold re-tuned. This is the failure
   [claim extraction](../../retrieval/design.md#claim-extraction--how-side-a-becomes-queries) already
   names: *"merged, a partial match reads as a match and two real mismatches
   disappear."* The count only held because they were unpacked by hand.
2. **Citation resolution fell 99% → 80%.** More citations written (74 → 148), a
   larger share wrong.

**The scoring lesson, which cost an hour.** A regex screen said the baseline
lacked findings #5 and #6. It had both — written in *words* rather than
identifiers (*"B unfreezes at epoch 4"*, not `UNFREEZE_EPOCH`). **Pattern
matching is a screen, never a score.** This file already warned: *"a miss you
have not looked up is not evidence about the model — it is evidence about your
scoring."* It happened again anyway.

**What this settles.** The remaining seven misses all require reasoning about **B
on its own terms**, with no A statement to anchor to. That is `find_bugs` and
`find_missing` — a loop with one focused call per unit. The measured split stands:

$$
\text{retrieval costs} \approx 2 \text{ findings}, \qquad
\textbf{the single call costs} \approx 7
$$

~~**So Step 2 is a requirement, not a design preference — and the numbers now say
so.** Stop tuning the prompt.~~

> **CORRECTED 2026-08-17, session 10.** The split above is real; the conclusion
> drawn from it was not. *"The numbers now say so"* rested on **one** clean run —
> every other post-fix run was truncated or litigating rule conflicts. And a
> single call **did** find those seven, once the question changed. The 7 belonged
> to the *question*, not to the *call*.
>
> **The explanation moved twice, each time right after a failure:**
>
> ```
> session 7  "no prompt fixes the seven, it is Step 2"
> session 7  retracted: "the prompt can, predict 15-16"
> session 9  "the prompt cannot, Step 2 is a requirement"
> ```
>
> That is the shape this file warns the *model* about in the §9 rule — bending
> the reading so the story closes. We did it to ourselves. **When a conclusion
> moves to protect a plan, re-read the artifacts before writing it down.**

**Two things changed under this task on 2026-08-16, and both affect the
measurement:**

1. **Tier 1 is now `gemini-3.7-flash`, not `gemini-3.6-flash`.** The 11/18
   baseline was set by 3.6. So a straight comparison changes **the prompt and the
   model at once** — the exact mistake this file warns about under
   [what the smoke run writes](../../prompts/comparison-template.md#what-the-smoke-run-writes). **Pin the model.**
   Either score the new prompt on 3.6 first, or run both models and report two
   numbers.
2. **`artifacts/` already holds unscored post-fix runs** from 2026-08-14/15,
   including `2026-08-15_00-16_core-stuffed_gemini-3.6-flash.md` — stuffed, tier
   1, on 3.6, with the fixes in. **That is the correct like-for-like comparison
   and it is already paid for.** Score that file before spending another request.

The one thing to hold on to: **the miss list is not random.** Every miss is
something B does that A never mentions, or something that needs reasoning over
B's own numbers. The prompt asks for neither. Start with the B-walk — it is one
instruction and it should be worth four findings.

Do not touch `ingest/`, and do not improve `select()`. Measure **stuffed**, so
retrieval is not a variable while the prompt is being changed.

