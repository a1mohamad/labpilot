# scripts/

Tools that are not part of the app: measurements, setup and repository chores.
Run them from the repository root, for example
`python -m scripts.setup.setup_checkpoints`. The older ones say
`PYTHONPATH=. python scripts/<folder>/<name>.py` at the top; both work.

| folder | what is in it |
|---|---|
| `setup/` | one-time setup: the chat tables, loading and embedding a corpus |
| `routing/` | keep the model routes up to date: free lists, speed, accuracy bench (see its README) |
| `models/` | probes of single providers and tiers: latency, tool calls, Routeway |
| `retrieval/` | Step 1 measurements: embedders, fusion, reranking, chunking, corpora |
| `answers/` | scoring of whole answers and claims against the answer keys |
| `timing/` | the clock of one question, node by node, and the benchmarks of time |
| `repo/` | repository chores (`merge_per_file.py`) |

Moved on 2026-11-21 from one flat folder; the map from the old paths is in
CLAUDE.md section 33.
