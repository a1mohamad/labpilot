# Full text: Slice 2 — DONE 2026-08-28: a repository becomes chunks

[Docs home](../../README.md)

## Slice 2 — DONE 2026-08-28: a repository becomes chunks

**Shipped:** `labpilot/sources/` — a **new adapter package** that turns a folder,
a `.zip` or a git URL into files, plus `chunk_source` in `api/services.py` that
turns those files into chunks. **Proven against real GitHub**, not only mocks.

| module | job |
|---|---|
| `contracts.py` | `Source` (the artifact) · `SourceFile` (one file in it) |
| `defaults.py` | the allowlist, the skip list, five limits |
| `errors.py` | `SourceError` and five subclasses |
| `_walk.py` | folder → files: prune, filter, count every skip, **yield** |
| `folder.py` · `archive.py` · `git.py` | the three openers, one `with` shape |

```
git clone --depth 1 https://github.com/a1mohamad/labpilot
  -> 100 files kept, 17 skipped (binary)
  -> 1,094 chunks, 251,017 tokens, max 544
  -> temp folder deleted
  -> 5.2 seconds
```

**428 passed, 28 skipped, 2 xfailed, ruff clean.**


### The five decisions worth keeping

**1. `sources/` is an adapter, not part of `ingest/`.** It runs `git`, extracts
archives and walks the filesystem — it talks to the outside world, so it is a
different **layer** from the pure logic in `ingest/`. *One pipeline, two layers,
and the layer decides the folder.* **Loading is a different story** — it is core,
the same layer as splitting, so it lives **inside** `ingest/` as a `LOADERS`
dict. See [loaders live inside ingest](../../step1/plan.md#loaders-live-inside-ingest--corrected-2026-08-28).

**2. The `with` shape exists for the other two.** A folder has nothing to clean
up. `open_folder` is written first *because* it is trivial, so the shape is
fixed before the cases that must delete a temp directory arrive.

**3. Prune directories; never filter afterwards.** `os.walk` re-reads the
`dirnames` list after our turn, so `dirnames[:] = sorted(...)` stops it
descending. `node_modules` is 200,000 files we never stat. **The `[:]` is the
whole trick** — `dirnames = [...]` moves our own label while `os.walk` keeps
reading the list it still holds.

**4. Sorting is correctness, not tidiness.** Chunk ids are positional. If folder
order shifts between machines, `B-42` names a different file and two reports stop
being comparable — which would throw away `temperature: 0` one layer lower.

**5. Refuse; never truncate.** An oversized tree raises `SourceTooLarge`. Half a
repository searched silently is the [orphan-chunk failure](../../retrieval/chunking.md#five-failure-modes-to-test-against)
wearing a different hat.


### The security work, and one claim of mine that measurement killed

| danger | what we do |
|---|---|
| **`git clone ext::sh -c ...`** runs a shell command — a documented git transport | accept **only `https://`**, and pass argv as a **list** with `--`, never `shell=True` |
| a symlink named `notes.py` pointing at our `.env` | `path.is_symlink()` → skip, and count it |
| a zip bomb: 1MB compressed, 10GB unpacked | check the **declared** total, then count the **real** bytes while writing |
| `git` hanging on a credential prompt | `GIT_TERMINAL_PROMPT=0`, plus a 120s timeout |

**And the claim that was wrong.** This file's own plan said *"naive `extractall`
writes outside your temp folder"*. Measured:

```
names in zip  : ['../../escaped.txt', 'C:/Windows/abs.txt', 'ok/good.py']
files written : ['escaped.txt', 'Windows/abs.txt', 'ok/good.py']
escaped above out? []
```

**CPython's `zipfile` already strips `..` and drive letters.** That is true of
`tarfile` historically, not of `zipfile`. We still validate — but for a
*different* reason: `extractall` **silently rewrites** the path, and a silent
rewrite is the failure this project bans. We refuse the archive instead.

> **Check the threat before writing the guard.** The guard survived; the reason
> for it did not — and a wrong reason is what gets copied into the next project.


### The Python trap that cost a red suite

`sources/__init__.py` exports a function named `walk` from a module named
`walk.py`. The `from ... import walk` **overwrites the module name with the
function name** in the package namespace, so
`monkeypatch.setattr("labpilot.sources.walk.MAX_FILES", ...)` resolved to the
*function* and three tests died with
`'function' object has no attribute 'MAX_FILES'`.

Fixed by renaming to `_walk.py`, the convention every other package already
follows (`_markdown`, `_python`, `_recursive`, `_http`, `_ids`).

> **A package's public name and one of its module names must never be the same
> word.** Nothing warns you — imports keep working, and only attribute-path
> tools like `monkeypatch` ever notice.


### What slice 2 deliberately did NOT do

- **The endpoint still accepts only two uploaded files.** Wiring a zip or a URL
  into `POST /api/v1/compare` would 413 immediately: the outline lists one line
  per chunk, and 1,094 chunks cost roughly 22,000 tokens. That is slice 7.
- **`chunk_source` is therefore unreachable from the app** — tested, but called
  only by tests. Scaffolding with a scheduled consumer, not dead code.
- **No zip integration test.** `test_archive.py` already runs zip → walk →
  relpaths, and by then all three openers have produced the same `Source`.
  *One test per distinct failure, not one per combination.*
