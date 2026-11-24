# Full text: The chunk cap fix — 2026-09-05, the last cheap moment

[Docs home](../../README.md)

## The chunk cap fix — 2026-09-05, the last cheap moment

*The oldest known bug in the project, carried as `xfail(strict=True)` since
2026-08-28. Fixed now for one reason: **the fix moves chunk boundaries**, and
nothing is stored yet. `write_artifact` still has no caller outside tests, so
re-chunking costs four embedding requests. After slice 7 wires ingest, the same
change would mean re-chunking **and re-embedding every stored corpus**.*

> **Fix chunk boundaries before pgvector holds anything, or not at all.**


### The bug

`MAX_CHUNK_TOKENS = 510` was enforced on `chunk.text`. What is actually sent to
the embedder and the reranker is `chunk.embed_text` — **header plus text**. So
the cap applied to the smaller half of the string.

| | before | after |
|---|---|---|
| `B_train.py` | 2 of 79 over, worst **526** | 0 of 82, worst **504** |
| whole repository | 43 of 1,094 over | **0 of 4,889**, worst **509** |

Two real consequences, not cosmetic: **BGE Base** declares a 512-token input
limit and refuses those chunks outright, and **Cohere auto-splits** any
document over 510, silently multiplying the billed rerank documents that this
file's budget arithmetic assumes.


### The fix — reserve the header before you cut, not after

The header could not simply be measured, because it is built **after** every
size decision and contains two things the split has not decided yet: the
`part i/n` suffix, and the line numbers.

So `_reserve` is deliberately **pessimistic**. It always allows for
`part 999/999` and for the widest line numbers the file can produce, then
`_budget = MAX_CHARS - _reserve`. Over-reserving costs a few characters of
chunk; under-reserving is the bug.

`split_recursive` now takes `max_chars`, threaded through `_blocks` and
`_pack`. One detail that is easy to miss: `_pack`'s target had to become
`min(TARGET_CHARS, max_chars)`, because `TARGET_CHARS` (1,500) sits just under
the old cap and would otherwise ignore a shrunken budget entirely.

**`_merge_small` had to learn the same budget.** A merge that only checked
`MAX_CHARS` could rebuild exactly the oversized chunk the split had just
avoided — the guard has to exist on both sides of the boundary decision.


### Re-scored, because boundaries moved

`B_train.py` went 79 -> 82 chunks, so slice 1's numbers described chunks that no
longer exist. Re-run with `scripts/retrieval/score_retrieval.py` — four embedding
requests, no generation quota:

```
after    recall@1 0.412   @5 0.941   @10 0.941   MRR 0.608
before   recall@1 0.412   @5 0.941   @10 0.941   MRR 0.613
```

**Recall is identical.** MRR moved by 0.005, which is one query moving one
place on a 17-query fixture. `D2` is still the known miss at rank 46. So the
cap is now honest and retrieval quality is unchanged.


### Mutation results — 2 of 3, and the survivor is honest

```
no header room reserved at all   -> the cap test, ALONE   (this was the bug)
packing target ignores the budget -> the cap test + the recursive fallback test
the +1 for the newline dropped    -> NOTHING
```

The `+1` accounts for the newline `embed_text` puts between header and text.
Nothing pins it, because the reserve is pessimistic enough that one character
of slack never shows on these fixtures. **It is kept as correctness in
principle and recorded as untested**, rather than described as something the
suite guards.


### The other xfail stays

`test_an_archive_we_accept_must_be_able_to_reach_us` is still
`xfail(strict=True)`: `MAX_ARCHIVE_BYTES` is 50MB against a body limit of about
10MB. Fixing it means choosing **which number moves**, and the endpoint accepts
no archive at all yet — that is slice 7's decision, and inventing the number
now would be a guess dressed as one. Only its `reason` was refreshed: it still
said "about 2MB", from before `MAX_UPLOAD_BYTES` rose to 5MB for PDFs.
