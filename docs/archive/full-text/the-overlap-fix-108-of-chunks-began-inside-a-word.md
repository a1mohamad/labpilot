# Full text: The overlap fix — 10.8% of chunks began inside a word

[Docs home](../../README.md)

## The overlap fix — 10.8% of chunks began inside a word

*Found while reading real Go, not by any test.*

```
chunk 2 of context.go:  'ntextRequestKey ContextKeyType = 0'    <- "Co" left behind
chunk 2 of _classes.py: 'om abc import ABCMeta, abstractmet'    <- "fr" left behind
```

`_pack` set each chunk's start to `block_start - OVERLAP_CHARS` — a **raw
character count**. It lands wherever it lands.

```
before   24 of 222 chunks began mid-word   (10.8%)
after     0 of 226                          (0.0%)
```

The fix is `_snap`: move the overlap start back to the beginning of a line, or
failing that past a space, never below the floor that keeps the chunk inside
`MAX_CHARS`. Six lines.


### The test that promised both ends and checked one

`test_a_word_is_never_cut_in_half` existed the whole time, and passed:

```python
assert all(p.text.endswith("word") for p in split_recursive(LONG_TEXT))
```

**`endswith` only.** Its name promised both ends of the chunk; it checked one,
and the unchecked end was exactly where the bug lived. It is now
`test_a_piece_never_begins_or_ends_inside_a_word`, asserting a real word
boundary at both ends, and reverting `_snap` makes it — and only it — go red.

> **The same family as `test_no_chunk_text_exceeds_the_hard_cap`.** A test named
> after an invariant must check the whole invariant, not the convenient half.
> Both were found by asking what the name claims, not by reading the assertion.

**A correction worth keeping:** my first replacement asserted
`startswith("word")` and failed — because every paragraph in the fixture
legitimately begins with the word `"paragraph"`. The code was right and the new
assertion was wrong. *Read the failure before blaming the code.*


### The re-score, which is why the fix was safe to make now

Chunk boundaries moved (`B_train.py` 78 -> 79 chunks), so slice 1's numbers
described chunks that no longer exist. Re-run on `queries.json` with
`codestral-embed`:

```
after    recall@1 0.412   @5 0.941   @10 0.941   MRR 0.623
before   recall@1 0.412   @5 0.941   @10 0.941   MRR 0.613
```

**Identical recall, MRR slightly up.** `D2` is still rank 42, the same known
miss. So the fix removed every mid-word chunk and cost nothing.

**It was cheap only because nothing is embedded yet.** No database, no stored
corpus, nothing deployed — the sole cost was four embedding requests. The same
change after slice 4 would mean re-embedding every corpus. **Fix chunk
boundaries before pgvector exists, or not at all.**


### `scripts/retrieval/score_retrieval.py` is now committed

Slice 1's scorer lived in a session scratchpad and was **lost**, so this session
rewrote it from nothing to answer a question CLAUDE.md says to ask after *every*
retrieval change. It is now a file in the repository.

```
PYTHONPATH=. python scripts/retrieval/score_retrieval.py
```

Four embedding requests, no generation quota.

> **A measurement you cannot repeat is a number, not a result.** If this file
> tells the next session to re-measure, the instrument belongs in the repository
> beside the fixture.


### The slice 3 closing review — one door had no guard at all

*Run as the last act of slice 3, asking the standing question across the whole
system rather than across the new code. **505 passed, 28 skipped, 2 xfailed.***

**Web files were an omission, not a decision.** `.html`, `.css`, `.scss`,
`.sass`, `.less`, `.vue`, `.svelte` and `.htm` were simply never listed, and it
was the user who noticed. Measured safe: real `.css` peaks at a max line of 746
and `.html` at 287, both far under the 1,530 guard, while `.min.css` is still
caught. `CODE_SUFFIXES` is now 58.

#### The finding: `.env` was refused by one door and accepted by the other

`READABLE_SUFFIXES` keeps a credentials file out of a **repository walk**. The
**upload endpoint** never consulted it — `read_artifact` checked only that a
filename *has* a suffix:

```
walk    prod.env  ->  skipped, "unreadable type"
upload  prod.env  ->  accepted, chunked, sent to a model provider
```

**That is the whole reason `.env` is excluded**, and half of it was missing.
`SECRET_SUFFIXES` now lives in `sources/defaults.py` — `.env`, `.pem`, `.key`,
`.p12`, `.pfx`, `.keystore`, `.jks` — and the door raises a typed
`SecretUpload` (422, `secret_upload`).

> **An allowlist protects the door that reads it.** When a rule exists for a
> security reason, walk every entrance before believing it is enforced.

Three tests, all mutation-verified: dropping the door guard fires the API test
alone; making `.pem` readable fires `test_no_secret_suffix_is_also_readable`
alone. (`.env` also trips an older test, but only because `env` happens to be a
skipped *directory* name — which is why `.pem` is the honest mutation.)

#### One test I wrote in the same pass was fake, and the mutation proved it

`test_a_readable_suffix_with_no_loader_is_really_plain_text` parametrized over
63 suffixes and looked thorough. Declaring `.zip` readable with no loader **did
not fail it** — because the test feeds *text* and every loaderless suffix
resolves to `load_text`, so the assertion could never fail. 63 green cases
proving nothing.

**Deleted.** The suite went 567 -> 505, which is the right direction.

> **A parametrized test is not 63 tests.** It is one assertion run 63 times, and
> if the assertion is trivially true it is trivially true 63 times over.
