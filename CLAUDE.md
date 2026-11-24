# CLAUDE.md — LabPilot

LabPilot compares a reference (A: a paper or original code) with a subject (B: the code
the user built), explains **why their results diverge**, and proposes the next experiment.
It is a learning project: RAG, vector databases, agents (LangGraph, MCP), fine-tuning.

**This file is the front page and is loaded every session. The text is in [docs/](docs/README.md).
Open only the pages the task needs** (the table below). Start with
[the current status](docs/status/current.md).

## ⛔ The reader — applies to EVERY reply, in EVERY session

The user is a **beginner in agents, graphs, LangGraph, LangChain, MCP, the inside of RAG and
fine-tuning**, and their English is **B1-B2**. They know PyTorch, FastAPI, Docker and Postgres well.

1. Write the WHOLE reply for this reader: lessons, reports, errors, questions. They must never
   have to remind you.
2. **Never an opener line or a one-line definition at the top instead** (they called it cheating).
   Explain each agent word where it is first used, in common words, tied to something they know.
3. One tiny real example beside every rule. Common words, full sentences ("because", "so"), no
   idioms, no metaphors. Do not copy expert words from the docs: translate them.
4. Short: about one screen. If the user says they are confused, stop adding ideas.
5. Before sending: is every agent word explained? Could a B1 reader follow it? About one screen?

Teaching order for a NEW concept: the concept, the details, the math, its place in the pipeline.
A question about existing code gets a plain walk-through, not a lesson.
→ [Teaching and communication](docs/rules/teaching-and-communication.md)

## Rules that always bind

- **The user types ALL product code.** Claude gives it in the chat; tests are copy-paste. Claude
  edits product files only when the user asks in words. Scratch copies live outside the repo, and
  Claude says so. Lessons go in the chat, never in files. A step is given WHOLE in one message.
  Never invent extra lessons: the lesson count of the plan is a promise.
- **Git.** Only the user commits to `main`. A new branch needs permission, every time. Commit only
  when asked. Commit messages go in ONE file, `artifacts/commit_messages.txt`, overwritten.
  → [Sessions and commits](docs/rules/sessions-and-commits.md)
- **Network first.** Before any call to a model, report the exit ISP and run a real Google
  `generateContent` probe. → [Sources and network](docs/rules/sources-and-network.md)
- **Honesty.** One run is noise; say the number of runs, the pair and the model beside every number.
  Two sources count for "free": the provider's own page and the real signup. No card, ever.
- **Tests with the code**, then **break one line and read WHICH test fires**, on a kept copy of the
  file; never restore with `git checkout`. → [Mutation testing](docs/development/mutation-testing.md)
- **Modular.** Layers, one front door per package, one reason to change per file. Say which file a
  new piece goes in before writing it. → [Modularization](docs/rules/modularization.md)
- **Do not design a node from one example**, and never write a prompt from the answer key
  (`EXPECTED.md` may score, never write). Every number is a guess until it is measured on many
  pairs. → [Rules for slice 13](docs/step2/27-slice-7-decisions-and-slice-13.md)
- **After every slice: a full closing review.** At the end of a session: a prompt to continue.
  Both without being asked.
- **Secrets** never in code, docs or git. `.env` is never committed.

## Docs rules (since 2026-11-24)

- **One truth:** each fact is on ONE page of `docs/`. There is no DETAILS.md any more.
- New work: write it on the page of its slice (`docs/step2/`), then update
  [current status](docs/status/current.md) and the row in
  [Step 2 progress](docs/status/step2-progress.md). Old text is corrected with a dated UPDATE
  note, not deleted.
- New decisions are table rows `| **D134** | ... |`, new measurements `| **M35** | ... |`, and
  numbers already used are never reused. After a docs change run
  `python -m scripts.repo.build_docs_index`, then `python -m pytest tests/unit/test_docs.py -q`.
- Keep this file under 16 KB. Details go to a page, with a link here only if every session needs it.
- "CLAUDE.md section 31.19" in a code comment or an old note means
  [the section map](docs/reference/section-map.md).

## What to read for which task

| task | pages |
|---|---|
| start any session | [current status](docs/status/current.md), the brief or page of the running slice |
| the running slice (12) | [slice 12 brief](docs/step2/slice-12-brief.md) and the pages it names |
| the whole Step 2 plan and slice list | [plan](docs/step2/00-plan.md), [final design](docs/step2/21-final-design.md), [progress](docs/status/step2-progress.md) |
| a decision (D..) or measurement (M..) | [decisions](docs/reference/decisions.md), [measurements](docs/reference/measurements.md) |
| write or review code | [code style and tests](docs/development/code-style-and-tests.md), [layers](docs/development/architecture-layers.md), [traps](docs/rules/traps.md) |
| models, quotas, routes | [slice 11](docs/step2/33-slice-11-routing.md), [routing guide](docs/step2/31c-routing-guide.md), [provider limits](docs/step2/30-chain-update-and-limits.md), `scripts/routing/README.md` |
| the prompts and the answer | [prompt rules](docs/step0/prompt-experiments.md), [comparison template](docs/prompts/comparison-template.md), [slice 6](docs/step2/17f-slice-6.md) |
| differences and bugs | [slice 9](docs/step2/29a-slice-9-findings.md), [follow-ups and saved results](docs/step2/29b-slice-9-followups.md) |
| search, rerank, embedding | [retrieval design](docs/retrieval/design.md), [ask path](docs/step1/ask-path.md), [Step 1 measurements](docs/step1/measurements.md) |
| chat memory and the database | [chat memory](docs/step2/17a-chat-memory.md), [vector store](docs/step1/vector-store.md) |
| the page, Step 3 | [UI](docs/product/ui.md), [build plan](docs/product/build-plan.md) |
| git history, branches | [branches](docs/status/git-and-branches.md) |

## Commands

```bash
source .venv/Scripts/activate        # Python 3.13; plain `python` outside it is 3.10
python -m pytest tests/unit tests/api -q      # no network, no database
python -m pytest tests/integration -q         # real Postgres (DATABASE_URL)
ruff check . && ruff format --check .
python -m scripts.setup.setup_checkpoints     # once per database (chat tables)
python -m scripts.repo.build_docs_index       # after every docs change
```

Smoke tests (`--run-smoke`) spend quota: never by default. Use `</dev/null` for Python in Git Bash.

## Stack in one line

FastAPI (`labpilot/api`, the entry) → LangGraph (`agent`, core) → our own LLM client
(`llm`: routes, race, health memory; `llm/registry/`: one file per gateway) + `embed`, `rerank`,
`sources`, `store` (Supabase Postgres + pgvector) → `ingest`, `prompts`, `retrieval` (core).
Adapters never import each other; core never imports adapters (`tests/unit/test_architecture.py`).
