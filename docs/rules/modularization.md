# Modularization

[Docs home](../README.md)

### Modularization — the whole app, not only `agent/` (rule added 2026-10-15, D45)

*The user asked for this more than once, and it was forgotten. It is written
here, in Working Rules, so that every session reads it before it writes or
teaches any code. The first version of this rule only talked about a big
`graph.py`. The user corrected it: the point is a well-modularized APP, and a
big file is only one symptom.*

**Five points. Every new piece of code follows them, and Claude says which
file a new piece goes in BEFORE a lesson starts.** (The details are in "Layout"
and "The four layers" in Conventions; this list is the short version.)

1. **Layers.** Shared, then adapters, then core, then entry. A new package is
   assigned to a layer on the day it is created.
   `tests/unit/test_architecture.py` enforces it.
2. **One front door per package.** Other code imports from `labpilot.<package>`,
   never from one of its files.
3. **One reason to change per file.** Ask: "when X changes, how many files do I
   touch?" Two jobs in one file means two files. A file past about 400 lines is
   a symptom to investigate, not a rule by itself.
4. **Contracts live alone.** Value objects and error types sit in small modules
   that import nothing from their package.
5. **Wiring is split by job too.** `agent/` is core, so `api/` hands it every
   function it needs (D7). Those functions are the place where a big file grows
   back, so they are not all collected in one `services.py`.

**`labpilot/agent/`, the package that grows most in Step 2.** From slice 3 on,
it is split by reason to change:

- `state.py` holds the `State` class alone. Node files and `graph.py` both
  import it, so there is no circular import.
- **Every node gets its own file.** It is a factory: it receives the injected
  functions (D7) and returns the node function. `summarize.py` first, then
  `planner.py`, `check.py`, `respond.py` and so on.
- `graph.py` holds only `build_graph`: it calls the factories, adds the nodes
  and draws the arrows.
- `__init__.py` keeps exporting `build_graph` and `State`.
- The six nodes from slice 2 (`measure`, `stuff`, `search`, `prompt`,
  `generate`, `remember`) stay in `graph.py` until a later slice touches them.
  Then each moves to its own file. For a while the package has both styles.
- The file names are the proposal of 2026-10-15. Slice 3 lesson 2 confirmed `state.py`, `summarize.py` and
  `graph.py` (17.17).
- **Before a lesson adds a node, Claude says which file it goes in.** A node
  written inside `build_graph` is a mistake, not a shortcut.

**What was measured on 2026-10-15** (only file sizes, layers and front doors;
the inside of the files was NOT read): 2 of 103 files are over 400 lines,
`api/services.py` (873 lines, two jobs: INGEST and ASK) and `llm/registry.py`
(1,273 lines, only data: the 73 model tiers, not urgent). 4 imports skip a
front door, all in `api/`: `reranking.py` to `llm.registry`, `services.py` to
`agent.graph`, `startup.py` to `llm.chain`, `uploads.py` to `sources.defaults`.

**DONE 2026-10-18: the task owed at the end of slice 3** (the user's decision of
2026-10-15). The whole app was read file by file, then `api/services.py` was split
and the rest was fixed. The full result is in 17.18. In short: the layers are
correct; `api/services.py` (873 lines, four jobs) became six files and was deleted;
`ingest/chunker.py` gave its size rules to `ingest/_sizing.py`; the 4 front-door
imports were fixed; `store/search.py` is now `store/vector_search.py`; `Source` in
`agent/` is now `Slot`. The old decisions stay: the six nodes of slice 2 leave
`graph.py` in slices 5 and 6, when those slices rewrite them, and `llm/registry.py`
is split later, by gateway, in slice 11.
