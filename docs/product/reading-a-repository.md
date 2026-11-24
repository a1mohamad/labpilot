# Reading a repository

[Docs home](../README.md)

### Reading a repository — Step 1, recorded 2026-08-11

All three input kinds collapse to one shape after the first step:

```
single file  ─┐
uploaded zip ─┼─▶ a folder on disk ─▶ walk ─▶ chunk ─▶ embed ─▶ pgvector
git URL      ─┘
```

Only the "get me a folder" step differs; everything downstream is shared.

**For a git URL: shallow clone into a temp directory, then delete it.**

```
git clone --depth 1 --single-branch <url> <tempdir>
```

- `--depth 1` fetches one commit, no history. LabPilot compares *current* code,
  and a repo with years of history can be 10× larger.
- The clone is **throwaway**. After ingest the chunks and vectors are in
  pgvector — *that* is the stored artifact. Delete the directory in a `finally`.
- Never a persistent volume.

**Filter before chunking, or the ingest budget is wasted on noise:**

| Skip | Keep |
|---|---|
| `.git/`, `node_modules/`, `venv/`, `dist/`, `build/` | source files |
| images, binaries, `*.lock`, `*.min.js` | `README`, docs |
| anything over ~1MB | notebooks |

**Cloning is safe in v1 because LabPilot only reads.** It never runs
`pip install`, never executes `setup.py`. A clone is inert text. This is exactly
why sandboxing (Incus, containers, VMs) is a **v2** question — v2 would execute
code, v1 does not.

**Stream the walk; never build the whole list.** Chunk and embed in batches of
~100, saving each batch before reading the next. The text is small (~4MB for a
repo) but the vectors are not: 2,000 × 1536 floats is ~12MB as numpy arrays and
**~73MB as Python lists of floats** — for data about to be written away. Batching
keeps it at ~4MB and costs nothing, since the loop exists regardless.
