---
name: mutation-test
description: Prove a test is real by breaking the code it guards. Use whenever a test is written that pins an INVARIANT - a rule that must always hold, not one example - before reporting the test as done and before the commit. Triggers on writing a threshold test, a registry or allowlist test, a layering or architecture test, a "no X may ever Y" test, a security guard, or any test whose name contains never/every/only/no. Also use when asked to verify, audit, or check whether existing tests are real, whether a test could ever fail, or whether a suite is honest. Do not use for an ordinary test - one happy path, one failure branch, or a parametrized list of values.
---

# Mutation testing

Break the thing the test guards. If the suite stays green, the test is fake.

## Why this exists

**Claude writes the tests in this project.** So the user cannot be the one who
remembers to check whether those tests are real. The obligation sits with
whoever wrote the test.

Three self-fulfilling tests were found in a single day (2026-08-17), all the
same shape - an assertion whose input was computed from the value under test,
so it could never fail:

```python
huge = b"x = 1\n" * (MAX_UPLOAD_BYTES // 3)   # raise the limit, payload grows
over = b"x" * (MAX_REQUEST_BODY_BYTES + 1)    # same bug, hours later
```

**Reading the tests caught none of them. Mutating the source caught all three.**
The rule *"a threshold test needs a literal on one side"* was written into
CLAUDE.md and violated again within hours. A written rule is not enough. A
performed check is.

## When to run it

**Only for an invariant** - a rule that must always hold:

| Run it | Skip it |
|---|---|
| a threshold or limit | one happy path |
| a registry, allowlist or blocklist | one failure branch |
| a layering or import rule | a parametrized list of values |
| a security guard | a value object being frozen |
| any name with never / every / only / no | anything the language guarantees |

## The procedure

### 0. Copy the file aside. Never restore with git.

```bash
cp labpilot/ingest/defaults.py /tmp/mutation-backup.py
```

`git checkout -- <file>` restores to whatever HEAD is **now**, not to what you
saved. This deleted finished work on 2026-08-29: a branch moved underneath the
mutation, and the undo became a delete. A file copy cannot be invalidated by a
branch someone else moves.

Committing first also works. The copy is safer, because it survives a branch
change.

### 1. Break exactly what the test guards - one line

Change the guard itself, not something near it. Lower a threshold to `0`,
remove a suffix from a registry, delete a `strip()`, swap a join separator,
point a model at a dead endpoint.

### 2. Run the suite

```bash
python -m pytest -q
```

### 3. Read WHICH test failed - not merely that one did

**This is the step people skip, and it is the whole check.**

"A mutation was caught" is not the verdict. "Which test caught it" is. That
question deleted `test_nothing_imports_the_entry_layer`, which could never fail
on its own because the layer rule always fired first - a comforting green line
that tested nothing.

### 4. Restore from the copy

```bash
cp /tmp/mutation-backup.py labpilot/ingest/defaults.py
```

### 5. Report the outcome in the message that delivers the test

Every time, before the commit, good news or bad.

## The three outcomes, and two of them are bugs

| Result | Verdict |
|---|---|
| **the new test failed** | ✅ real. Keep it |
| **nothing failed** | ❌ the test is **fake**. Fix it, then re-mutate |
| **something else failed, the new one never fires alone** | ❌ the test is **dead**. Delete it |

Deleting is a normal outcome, not a failure. The suite went 567 -> 505 in one
review pass and that was the right direction.

## A surviving mutation is not a verdict either

Prove the mutation actually changed behaviour before blaming the test.

`ET.ParseError` is a **subclass of `SyntaxError`**, so a mutation that stopped
catching broken XML still caught the error. The test looked dead. It was the
**mutation** that was broken.

## Five real cases from this project

Each one is a distinct way a green suite lies.

1. **A no-op mutation.** `ET.ParseError` is a `SyntaxError`, so removing the
   `except` changed nothing. Blame the mutation first.
2. **A test that never fired alone.** `test_nothing_imports_the_entry_layer` -
   the layer rule always fired first. Deleted.
3. **A fake parametrized test.** `test_a_readable_suffix_with_no_loader_is_really_plain_text`
   ran 63 green cases. Declaring `.zip` readable with no loader did not fail it,
   because every loaderless suffix resolves to `load_text` and the test fed it
   text. **A parametrized test is not 63 tests. It is one assertion run 63
   times.** Deleted.
4. **`git checkout --` deleted work**, because a branch moved underneath it.
   Hence step 0.
5. **A test that promised both ends and checked one.**
   `test_a_word_is_never_cut_in_half` asserted only `endswith`. The bug lived at
   the other end - 10.8% of chunks began mid-word. **A test named after an
   invariant must check the whole invariant, not the convenient half.**

## Two traps that produce a fake test

**A threshold test whose input is computed from the threshold.** Use a fixed
literal on one side, plus an explicit premise assertion:

```python
huge = b"x" * 6_000_000
assert len(huge) > MAX_UPLOAD_BYTES   # fails loudly if the limit is ever raised
```

**A test that calls the function directly instead of through the registry.**
Every `.docx` test called `load_docx` by name, so removing `.docx` from
`LOADERS` broke nothing - **nothing proved the loader was wired in at all**. Go
through the real door.

## Do not automate this

No `mutmut`, no `cosmic-ray`. They mutate everything and are slow over 500+
tests on an 8GB machine. The targeted manual version costs seconds, because the
invariant that was just written is already known.

## Reporting shape

```
mutation: MIN_PDF_WORDS_WITH_VOWELS = 0.40 -> 0.0
result:   1 failed - test_a_pdf_of_glyph_names_is_refused
verdict:  real, and it fires alone
```

One block per invariant. Say the mutation, the test that fired, the verdict.
