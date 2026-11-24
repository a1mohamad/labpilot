# Step 1, slice 2: repositories, archives and git

[Docs home](../README.md)

## Slice 2 — DONE 2026-08-28: a repository becomes chunks

**Shipped:** `labpilot/sources/`, a **new adapter package** that turns a folder, a `.zip` or a git URL into files, plus `chunk_source` in `api/services.py` that turns those files into
chunks. **Proven against real GitHub**, not only mocks: `git clone --depth 1 https://github.com/a1mohamad/labpilot` → 100 files kept, 17 skipped (binary), **1,094 chunks, 251,017
tokens, max 544**, temp folder deleted, 5.2 seconds. 428 passed, 28 skipped, 2 xfailed, ruff clean.

Modules: `contracts.py` (`Source` the artifact, `SourceFile` one file) · `defaults.py` (the allowlist, the skip list, five limits) · `errors.py` (`SourceError` + five subclasses) ·
`_walk.py` (folder → files: prune, filter, count every skip, **yield**) · `folder.py`, `archive.py`, `git.py` (the three openers, one `with` shape).

### The five decisions worth keeping

1. **`sources/` is an adapter, not part of `ingest/`**: it runs `git`, extracts archives and walks the filesystem (the outside world), a different **layer** from the pure logic —
   *one pipeline, two layers, and the layer decides the folder.* **Loading is core**, the same layer as splitting, so it lives **inside** `ingest/` as a `LOADERS` dict (see
   [loaders live inside ingest](plan.md#loaders-live-inside-ingest--corrected-2026-08-28)).
2. **The `with` shape exists for the other two:** a folder has nothing to clean up, and `open_folder` is written first *because* it is trivial, fixing the shape before the cases that
   must delete a temp directory.
3. **Prune directories; never filter afterwards.** `os.walk` re-reads the `dirnames` list after our turn, so `dirnames[:] = sorted(...)` stops it descending (`node_modules` is 200,000
   files we never stat). **The `[:]` is the whole trick**: `dirnames = [...]` moves our own label while `os.walk` keeps reading the list it holds.
4. **Sorting is correctness, not tidiness.** Chunk ids are positional; if folder order shifts between machines `B-42` names a different file and two reports stop being comparable
   (throwing away `temperature: 0` one layer lower).
5. **Refuse; never truncate.** An oversized tree raises `SourceTooLarge`; half a repository searched silently is the [orphan-chunk failure](../retrieval/chunking.md#five-failure-modes-to-test-against) in
   a different hat.

### The security work, and one claim of mine that measurement killed

| danger | what we do |
|---|---|
| **`git clone ext::sh -c ...`** runs a shell command (a documented git transport) | accept **only `https://`**, argv as a **list** with `--`, never `shell=True` |
| a symlink named `notes.py` pointing at our `.env` | `path.is_symlink()` → skip, and count it |
| a zip bomb: 1MB compressed, 10GB unpacked | check the **declared** total, then count the **real** bytes while writing |
| `git` hanging on a credential prompt | `GIT_TERMINAL_PROMPT=0`, plus a 120s timeout |

**The claim that was wrong:** this file's plan said "naive `extractall` writes outside your temp folder". Measured: names `['../../escaped.txt', 'C:/Windows/abs.txt', 'ok/good.py']`
→ files written `['escaped.txt', 'Windows/abs.txt', 'ok/good.py']`, nothing escaped. **CPython's `zipfile` already strips `..` and drive letters** (true of `tarfile` historically,
not `zipfile`). We still validate, for a *different* reason: `extractall` **silently rewrites** the path, and a silent rewrite is the failure this project bans, so we refuse the
archive. > **Check the threat before writing the guard.** The guard survived; the reason for it did not, and a wrong reason is what gets copied into the next project.

### The Python trap that cost a red suite

`sources/__init__.py` exports a function `walk` from a module `walk.py`; the `from ... import walk` **overwrites the module name with the function name** in the package namespace,
so `monkeypatch.setattr("labpilot.sources.walk.MAX_FILES", ...)` resolved to the *function* and three tests died with `'function' object has no attribute 'MAX_FILES'`. Fixed by
renaming to `_walk.py` (the convention of `_markdown`, `_python`, `_recursive`, `_http`, `_ids`). > **A package's public name and one of its module names must never be the same
word**; nothing warns you, only attribute-path tools like `monkeypatch` notice.

### What slice 2 deliberately did NOT do

The endpoint still accepted only two uploaded files (wiring a zip or URL into `/compare` would 413 immediately: the outline listed one line per chunk, 1,094 chunks ≈ 22,000 tokens;
slice 7). `chunk_source` was unreachable from the app (scaffolding with a scheduled consumer). No zip integration test (`test_archive.py` already runs zip → walk → relpaths; *one
test per distinct failure, not one per combination*).

## The slice 2 audit — 2026-08-28

*Run at the user's request, asking the same question as the [2026-08-17 audit](../step0/slice-5-and-the-api.md#the-system-wide-audit--2026-08-17): **which real failure is still unprotected?** Three findings, and
measurement killed the second.*

**1. A test whose name promised more than it checked.** `test_no_chunk_exceeds_the_hard_cap` asserted `estimate_tokens(chunk.text) <= MAX_CHUNK_TOKENS`, but **what is sent to every
embedder and reranker is `chunk.embed_text` (text plus header)**. Measured on a real corpus: max `chunk.text` 497; **max `chunk.embed_text` 519** (`labpilot/` only) · **544**
(whole repo); over the 510 cap **2 of 232 · 43 of 1,094**. The test was green while the cap was broken for the only string that matters (the shape of
`test_the_documented_failures_are_the_ones_the_endpoint_can_raise`). **A test named after an invariant must check that invariant, not a cousin of it.** Fixed two ways, neither
hiding the defect: renamed to `test_no_chunk_text_exceeds_the_hard_cap` (honest name) and added `test_no_chunk_exceeds_the_hard_cap_once_its_header_is_added` marked
**`xfail(strict=True)`** (fails today; when slice 3 moves the cap onto the string we send it XPASSes and the suite goes red, forcing someone to delete the marker; mutation: making
`embed_text` drop the header gives `[XPASS(strict)] 1 failed`). > `xfail(strict=True)` is how a **known bug we own** stays visible; `strict=False` is for things outside our control (a
dead provider, a blocked region). *(Fixed 2026-09-05, "the chunk cap fix".)*

**2. The batch-budget claim — flagged, then killed by measurement.** `test_a_full_batch_of_capped_chunks_fits_the_tightest_token_budget` reasons `MAX_BATCH_SIZE × MAX_CHUNK_TOKENS ≤
TIGHTEST_TOKENS_PER_MINUTE` and finding 1 means that bound is not held — but measured: claimed `96 × 510 = 48,960 ≤ 50,000`; **real worst batch of 96 = 27,310**, real chunks average
**229** tokens. **The derivation is formally void and practically safe**, so the test stays; a replacement measuring real chunks was written and **deleted** (a 1.8× margin is a
number, not a guard).

**3. Nothing checked that our chunks fit the embedders we ship.** BGE declares `max_input_tokens=512`; an embedder whose limit is below `MAX_CHUNK_TOKENS` can never embed this
corpus (`_check_texts` would refuse every call). `test_every_embedder_can_take_a_chunk_at_our_cap` now parametrizes over `MIGRATION` (mutation: BGE lowered to 256) — the downstream
consequence of finding 1, caught at build time rather than runtime.

**Measured while auditing, and it corrects this file: streaming saves 2×, not the 73MB implied** — 4,108 chunks in the working tree: streamed **4.7 MB** peak, materialised **9.9
MB**. The 73MB figure was about **vectors**, not chunks, so the rule is right and its payoff is deferred to slice 4 (so the rule is not quietly over-sold).

### The three defects, and how each was closed — 2026-08-28

*Found by the audit, fixed the same day; all mutation-tested (removing each guard breaks exactly one test).*

1. **`os.walk` silently swallowed unreadable directories. FIXED.** Its default is `onerror=None`, so on Linux a permission-denied subdirectory vanished with no entry in
   `source.skipped`, breaking "nothing may be dropped silently"; `walk` now passes an `onerror` callback recording `unreadable directory`. > **A default that ignores errors is a
   silent-drop waiting to happen; read the default of every traversal API you use.**
2. **One unreadable file aborted the whole ingest. FIXED** in both places: `chunk_source` caught only `UnicodeDecodeError`, and `_reason_to_skip` could raise from `stat()` if a file
   vanished between listing and reading (an editor or antivirus holding it); both now catch `OSError` and count `unreadable file`. The fix also removed a double `stat()`:
   `_reason_to_skip` is now `_inspect`, returning `(reason, size)` from **one** `stat`, using `S_ISREG` instead of a second `is_file()`. **`Source.skip(reason)` was added** because two
   layers each hand-wrote `skipped[reason] = skipped.get(reason, 0) + 1` (counting belongs to the object that owns the count).
3. **`MAX_ARCHIVE_BYTES` (50MB) can never arrive through the API** (`MAX_REQUEST_BODY_BYTES` ~2MB). ⏸ **Pinned, not fixed**: fixing it means choosing whether the archive limit
   falls or the upload limit rises, a policy for a feature that did not exist; inventing a number would be a guess dressed as a decision. The relationship is written down as
   `test_an_archive_we_accept_must_be_able_to_reach_us`, `xfail(strict=True)`, so slice 7 could not wire an archive into the endpoint without the suite going red. > **A limit the
   system can never reach is a lie; when you cannot yet choose the number, pin the relationship the numbers must satisfy.** *(Closed in slice 7: 10MB; later both limits 10MB.)*

