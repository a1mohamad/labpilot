# Commits, branches, dependencies, secrets

[Docs home](../README.md)

### Commits
**Conventional Commits** — `<type>: <short imperative description>`, lowercase,
no full stop at the end.

```
feat: add LLM fallback chain
fix: handle empty retrieval result
docs: add CLAUDE.md
chore: add project dependencies
```

Types in use: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.

### Branching
**Creating a branch needs the user's permission, every time.** *(Rule added
2026-10-11, after Claude made a new branch for a small edit to CLAUDE.md.)* It
overrides every older line in this file, in DETAILS.md and in Claude's memory that
says to "branch first".
- Ask before `git switch -c`, `git checkout -b` or `git branch <name>`, and say what
  the branch would be for.
- If a suitable branch already exists, use it and say which one. Do not make another.
- Claude never commits on `main` (below). So when Claude is on `main` and a commit
  is needed, Claude stops and asks which branch to use or whether to create one. It
  never invents a branch to avoid asking.
- Reading files, running tests and editing files in the working tree need no branch
  and no permission.

**Branch per slice, not per commit.** *(Changed 2026-08-09 — this file used to
say "commit directly to `main`".)* Nobody is waiting to review, but this is a
portfolio repo, and a PR is also the only way to run a multi-agent code review.

- One branch per slice of work: `feat/llm-client`, `feat/fallback-chain`,
  `feat/retrieval`, `docs/readme`. Commit freely on the branch, however messy.
- **Squash on merge**, so `main` gets one clean commit per slice. Delete the
  branch after.
- Stay on `main` for small things with nothing to review — doc edits, folder
  creation, `requirements.txt`.
- Do not let a branch live for weeks. One slice, a few days, merge, delete. A
  long branch drifts from `main` and merging becomes painful.

**Never commit on `main`. Only merge into it.** *(Learned the hard way
2026-08-14.)* CLAUDE.md was being kept current on `main` by copying the file
across — `git checkout feat/retrieval -- CLAUDE.md` plus a separate commit on
`main`. That creates an **independent** commit touching the same lines, so git
sees two unrelated edits to one region and stops with a conflict. It has no way
to know both came from the same source.

The fix is a rule, not a technique: **edit every file on the branch; `main`
receives and never writes.** Then the two sides can never disagree, and the
merge is a fast-forward.

*(The `--squash` was not the cause. The double editing was. `--no-ff` was used
in the end so all 26 commits kept their own messages on `main` — a deliberate
override of the squash rule above, at the user's request.)*

### Dependencies
`requirements.txt` holds **direct dependencies only**, with pinned versions —
not the full `pip freeze` output. Rationale: readability. Once LangChain and
LangGraph arrive, a full freeze would be 100+ unreadable lines.

Planned progression (climb only when the project earns it):

| Stage | Setup | Trigger |
|---|---|---|
| ~~Now~~ | ~~one `requirements.txt`~~ | ~~4 packages, no tests~~ |
| **Now (Step 0)** | `requirements.txt` + `requirements-dev.txt` | reached early — tests are written alongside the code, so `pytest` arrives in Step 0, not Step 1 |
| Step 3 | `pyproject.toml` + lock file | Docker needs reproducible builds |

Note: `requirements.txt` is generated on Windows and may contain Windows-only
packages (e.g. `colorama`). Watch for this when the Docker image is built.


### Secrets
Never commit `.env`. Never put keys in code or in this file. Verify with
`git status` before every commit.

