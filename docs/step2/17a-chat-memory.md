# Section 17.1 to 17.8: chat memory, storage and cleanup

[Docs home](../README.md)

### 17. CHAT MEMORY, STORAGE AND CLEANUP — decided 2026-10-06

*Talked through with the user in plain words, one question at a time, right
before slice 2. The user agreed with 17.3 to 17.5. 17.6 is a plan for LATER, not
for slice 2. Nothing in this section is built. It refines D15 in section 10.7.*

#### 17.1 What was checked first (2026-10-06)

- **Git.** Branch `fix/mistral-dead-tiers`: 4 commits that exist only on the
  user's computer (not pushed, not in `main`). `main` equals `origin/main`. Open
  question for the user: push and merge that branch first, or start slice 2 from
  it. Nobody commits to `main` except the user.
- **Tests that never use the database:** `tests/unit` and `tests/api`, run with
  no database and no quota: **986 passed, 5 skipped, 0 failed**, ruff clean. The
  5 skips are not about the database: 4 are embedder checks that do not apply to
  some embedders, 1 needs admin rights to make a symlink on Windows.
- **Tests that DO use the database:** `tests/integration` holds **83** tests
  marked `database`. They use the real Supabase through the VPN, each run in its
  own temporary schema, no model quota. **They were NOT run on 2026-10-06.**
  `tests/smoke` spends model quota and was not run either.
- **Code.** `labpilot/agent/` is empty. `langgraph 1.2.12` is pinned and
  installed, and nothing imports it. `ask()` in `api/services.py` is the function
  slice 2 replaces; the route that calls it is `api/routers/compare.py`.
- **Numbers.** `CHAIN` has 56 tiers, the rerank chain 13, `MIGRATION` 8. The Chain
  1 table in this file still lists 40 tiers (see the note above it).

#### 17.2 How the memory works, in plain words

- **State** is one dictionary that moves from node to node. A node (one step, one
  function) returns only the fields it changed, and LangGraph puts them in.
- **Two kinds of memory.** Inside one run (one user message, from question to
  answer) the state moves from node to node with NO checkpointer. Between runs
  (the next message of the same chat) the state exists only with a checkpointer.
- **A checkpointer** saves a copy of the state after every step. Each copy is a
  checkpoint. A new message starts from the LATEST copy of its chat. The older
  copies matter only to continue after a crash in the middle of a run (one report
  can take minutes).
- **A `thread_id`** is the name of one chat. Same id, same saved state. A new id
  starts with an empty state. It is NOT the `request_id`, which is new for every
  request and exists for logs.
- **A reducer** is the rule that says how a new value joins the old one. By
  default it REPLACES (`question`, `answer`). For a list that must grow
  (`history`, `findings`) the rule is ADD.
- **Chat agents and memory.** The model remembers nothing: the program sends the
  old messages again in every call. When that gets too long there are three
  ways: cut the oldest messages, summarize them, or keep facts outside the chat
  and load only what is needed.

Tiny example, one chat `"chat-7"`:

```
turn 1   start          {"question": "why do results differ?", "chunks": [], "answer": ""}
         after search   {"question": "...", "chunks": [c1, c2], "answer": ""}      <- saved
         after answer   {"question": "...", "chunks": [c1, c2], "answer": "..."}   <- saved
turn 2   loads the last saved copy, replaces "question", runs again
         ("and what about the learning rate?" can now be read as a follow-up)
```

#### 17.3 Decisions

| # | decision |
|---|---|
| **D17** | **One chat = one `thread_id`.** The server makes a random uuid on the first message (when none is sent), returns it in the response, and the page keeps it in the browser so a refresh continues the chat. Random, never 1, 2, 3: there is no login, so anyone who knows the id could read the chat. **BUILT 2026-10-13 as D38** (17.14): the request has an optional `thread_id`, and the reply always carries one |
| **D18** | **Slice 2 ships a checkpointer.** Same as D15. The saved state is the memory between turns |
| **D19** | **The state is saved in Postgres, in the SAME Supabase database, in separate tables** (the user agreed, 2026-10-06). The saver in memory is for tests only, because Render restarts the server and a memory saver loses every chat. The saver needs a new package, `langgraph-checkpoint-postgres`, which is installed and pinned now (see the end of this row). **Slice 2 had to check first** its name and version, that it works with our `psycopg 3.2.12`, and that it works on the session pooler (port 5432, never 6543: transaction mode rejects prepared statements) **CHECKED 2026-10-11 (17.12) and BUILT 2026-10-13 (17.14): `langgraph-checkpoint-postgres==3.1.2` and `langgraph-checkpoint==4.2.0` are pinned, the four chat tables exist in the real database, and it works on the session pooler.** |
| **D20** | **What the state holds** (17.4). The exact fields are decided in slice 2 |
| **D21** | **The prompt gets the recent questions and the `findings`, NOT the old full reports.** A report is about 5,000 tokens and `PROMPT_BUDGET` is 26,000. The list of findings is already the summary. A cheap model may summarize old turns later, ONLY if measured to be needed: Gemma has 14,400 calls a day, but every call adds waiting time and generation time is already the biggest problem |
| **D22** | **Keep only the latest copy of each chat.** The saver keeps a copy after every step, and a growing list is saved in full again at every turn, so old copies add up fast. **DECIDED AND BUILT 2026-10-13 (17.14): our own SQL, `PRUNE` in `api/checkpoints.py`.** `delete_thread` removes only a whole chat, and `ShallowPostgresSaver` was not used. It runs right after each message finishes, see D35. |
| **D35** | **THE CLEANUP OF OLD COPIES RUNS RIGHT AFTER EACH MESSAGE FINISHES** (the user agreed, 2026-10-11). `api/` runs the graph, gets the answer, and then deletes the older copies of THAT `thread_id` and keeps the newest. Why then: the run is over, so the in-between copies (useful only to resume after a crash in the middle of a run) are useless, and deleting them during the run would remove that protection; a timer is a bad fit because Render's free server sleeps when idle (the same reason as 17.6); it is one small delete per message; and it repairs itself, because a crashed run never reaches the cleanup and keeps its copies until the next finished message deletes them. If the cleanup itself fails, write a log line and still send the answer; the next message tries again. **How** to delete was decided in 17.14: our own SQL. Deleting WHOLE old chats and old artifacts is a different job: artifacts are D23 (Step 3) and chats by age are not decided |
| **D36** | **The graph saves ONCE, at the end of the message: `durability="exit"`** (2026-10-13). By default the graph saves after every step, and each save writes several rows. Over the VPN that is slow, and the in-between copies are deleted right after anyway (D35). The price: if the server dies in the middle of a message, that message is lost and is not resumed. The user asks again. Measured with a fake model function on the real database: the default saves 6 copies (~460 KB) and takes 4.5 to 6.5 s per message; with `exit` and the prune it stays at 1 checkpoint and 4 blobs per chat (~160 KB) and takes about 1 s |
| **D37** | **The saver only accepts the classes that are on a list** (2026-10-13). `JsonPlusSerializer(allowed_msgpack_modules=SAVED_TYPES)` with `Chunk`, `ArtifactRecord`, `StoredArtifact`, `Attempt` and `LLMResult`. A class that is NOT on the list does not raise an error: it comes back as a plain dict and leaves one log line, so the code that reads it fails later in a strange place. A new class in `State` must be added to `SAVED_TYPES`. `tests/api/test_checkpoints.py` checks the type that comes back |
| **D38** | **The server makes the chat id, D17 as built** (2026-10-13). `thread_id = (body.thread_id or "").strip() or uuid.uuid4().hex`, so a missing id and a blank id both start a new chat. The reply always carries the id. The page keeps it in `localStorage` under `labpilot.thread` and sends it with every question |

#### 17.4 What the state holds (D20)

```
keep for the whole chat (grows):     a, b          the two artifact ids, set once
                                     history       each turn's question and answer, short
                                     findings      what was found so far (ADD reducer)
this turn only (replaced next turn): question, chunks (ids, not text), answer
never in the state:                  the database connection (it cannot be saved),
                                     the full prompt (~78,000 characters, build it again),
                                     API keys
```

**The connection also cannot be in the state for a second reason:** `agent/` is the
core layer and may not import `store/`, `llm/`, `embed/` or `rerank/`
(`test_architecture`). So `api/` hands each node the function it needs, and the
connection stays inside that function (D7).

#### 17.5 How much space, and the free second project

**These numbers are rough estimates, NOT measurements.** Slice 2 measures one real
chat.

- One answer is about 12 KB of text. Chunk text adds about 25 KB per turn. With
  chunk ids only, almost nothing.
- One chat of 10 turns: about 120 KB (ids only) or about 400 KB (with chunk
  text). 100 chats: about 12 MB or 40 MB.
- One artifact of 10,000 chunks is about 90 MB, and a big repository is 200 MB or
  more. **The artifacts, not the chat state, are the real danger for 500 MB.**
- An earlier guess of 100 to 200 KB per turn was too high.

**Second Supabase project.** Read from Supabase's own pricing page on 2026-10-06:
the free plan allows 2 active projects, each with its own 500 MB database and its
own compute, and free projects are paused after 1 week of inactivity. The page
does not say whether a card is needed: we only find out when we create one, and
we stop if it asks. We already use 1 of the 2 slots. **Decision: do NOT create it
now. Keep it in reserve.** If the artifacts fill the first database, the second
project is worth more to them than to the chat state. It is only a new connection
string, because both are Postgres.

#### 17.6 Artifacts are never deleted, and the plan for it (D23, for LATER)

**Facts, checked in the code on 2026-10-06:**

- `store/schema.sql` has one `artifacts` table and one `chunks` table for
  everyone. There is NO owner column: no user id and no chat id. All artifacts
  from all chats share one database and one 500 MB.
- The id is `side + sha256(content)[:16]`. The same file in the same slot is the
  same artifact, stored once (re-ingest replaces it). Two different users who
  upload the same file share it.
- **Nothing deletes an artifact.** The routes are only `POST /artifacts`,
  `POST /compare` and the health routes. There is no delete route and no expiry.
  So the artifact data only grows, and when 500 MB is full every new upload fails.
- There is **no privacy between users**: anyone who knows an artifact id can ask
  about it.
- A chat only points to its two artifact ids. Deleting a chat does not delete
  artifacts. Deleting an artifact leaves chats that point to nothing.

**Plan (Step 3, before real users come; NOT slice 2):**

1. Add a column `last_used_at` to `artifacts`, updated at every `/compare` that
   uses the artifact. `alter table ... add column if not exists`, like the `tsv`
   column.
2. Before each ingest, read the size the database uses (one SQL query, for
   example `pg_database_size`).
3. If it is above a limit, delete the artifacts used longest ago until there is
   room. `on delete cascade` already removes their chunks.
4. The check runs at upload time, NOT on a timer: Render sleeps when idle, so a
   timer is not reliable. It also deletes only when space is really needed, which
   a rule like "delete after 7 days" does not.
5. The page tells the user before an upload that old files can be removed. If a
   chat comes back to a removed artifact, the existing `UnknownArtifactId` (404)
   is shown as: "this file was removed to free space, please upload it again".

**The limit of about 350 MB (70% of 500) is a guess to be measured.** Open: an
owner column for privacy, and what to do with chats that point to a removed
artifact.

#### 17.7 What slice 2 must do first, so nothing is forgotten

1. Teach the user the idea (this is the heavy teaching slice), THEN build.
2. Check `langgraph-checkpoint-postgres` (D19, checked 2026-10-11) and how to delete old
   copies (D22). The cleanup runs after each message finishes (D35).
3. Add `thread_id` to the compare request and response (D17).
4. Keep the state small (17.4) and measure one real chat (17.5).
5. Nodes take functions from `api/` (D7). The graph replaces `ask()` and
   NOTHING else moves: same answer, same response, same error mapping. The
   existing `ask` and `/compare` tests are the safety net.

#### 17.8 The lesson plan for Step 2, and who writes the code — 2026-10-06

**The user writes ALL the code. Claude brings it in the chat.** Claude does not
write files in `labpilot/`. Claude reads files, runs the tests, and runs the
mutation checks (break one line for a moment, put the file back from a COPY, and
tell the user first).

**One lesson** is one short message: the idea in plain words, one tiny example,
then 15 to 40 lines for the user to type. Then the user says "done", Claude runs
the tests, and every file gets its own commit. Lesson size: heavy is 3 or 4
lessons, medium is 2, light is 1, none is a measurement with no new idea. These
are estimates, not promises.

| Slice | What we do | Lessons |
|---|---|---|
| 0 done | does LangGraph fit 512 MB (yes, about 55 MB) | none |
| 1 done | the speed of each of the 56 models | none |
| **2 (DONE 2026-10-14: lessons 1 to 4 and the closing review, 17.14)** | replace `ask()` with a graph that gives the same answer, and add chat memory (checkpointer + `thread_id`) | **heavy, 4** |
| 3 | `summarize` for A and for B at the same time (two independent steps run together) | medium, 3 |
| 4 | the planner: one call chooses the steps and writes the queries. **Preceded by a small lesson on function calling (D34)** | medium, 5, **DONE 2026-10-19** (17.19, 17.20) |
| 5 | run the plan: a search for each query at the same time, merge and remove duplicate chunks, the final `respond` node | **heavy, 3, DONE 2026-10-21** (17.22, 17.23) |
| 6 | follow-up questions: rewrite them into standalone ones, and `respond` for 0, 1 and 2 files | medium, 2, **DONE 2026-10-22** (17.24) |
| 7 | the loop: claims, check each one, search again at most 2 times | **heavy, 3** |
| 8 | a step that can STOP the graph (the gate: one call on the two summaries, D78, section 28) | medium, 2 |
| 9 | the nodes for problems in B alone: `find_missing` and `find_bugs` | medium, 2 |
| 10 | results and the ask-the-user pause, and the planner choices of D107 (REDESIGNED 2026-11-12, section 31) | medium, 3 to 4 (DONE 2026-11-14) |
| 11 | each step gets its own models, token limit and thinking level | light, 1 |
| 12 | the size gate and big repositories (was slice 9) | medium, 2 |
| 13 | score the findings against the answer key and time the run | none |
| 14 | Jev for decisions: the decision model on the jobs of D73, one schema for each job (added 2026-10-23). **All the work on Jev is kept in THIS slice (the user's rule, 2026-10-28): every measurement of it and every code change for it. The check of a claim was measured once in the pilot M15 (25.5: Jev 27 to 29 of 32 claims, 10 to 30 times faster than the LLM checkers, not proven). Slice 14 takes NEW measurements of Jev on the check and on the other jobs. If they agree with 25.5, Jev is added. Other slices put no Jev code in the graph.** | not decided |

**The 4 lessons of slice 2:** (1) state, node and edge, with a graph of 2 steps;
(2) a list that grows, with a reducer; (3) chat memory: the checkpointer and the
`thread_id`; (4) cut `ask()` into steps that receive their functions from `api/`.

**How a new session continues (updated 2026-10-22):** slices 0 to 6 are DONE. Read the Phase paragraph of Current Status and the last section of 17 (17.24), check git (branch, status, `git log -5`), and continue with slice 7 (claims, check, retry; D4, D39, D40). The prompt that the last session gave the user is the best start (Working Rules, "Review pass after every slice, and a hand-off prompt at the end of every session"). **Two rules the user set (17.13) still hold: they type ALL product code
(only tests are copy-paste), and a step is given WHOLE in one message.** Lessons call no model, so
the exit-ISP check is not needed until the first live test. The chat tables must exist in the
database the app uses: run `python -m scripts.setup.setup_checkpoints` once from the repository root
(17.14). Since 2026-10-14 that script also locks the four tables (17.15). **The lesson scripts named
in 17.9 to 17.13 as `scripts/<name>.py` now live in `examples/langgraph/`.**
