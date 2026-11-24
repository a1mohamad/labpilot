# Section 17.9 to 17.15: slice 2, the skeleton

[Docs home](../README.md)

#### 17.9 Where we stopped — slice 2, lesson 1 is DONE, 2026-10-07

**Status when written (2026-10-07): lesson 1 of 4 was complete and lesson 2 was next. Lesson 2 is
now done (17.10) and lesson 3 is done too (17.11).** Nothing in
`labpilot/` was changed. `labpilot/agent/` is still empty and `ask()` is untouched.

**What the user typed and ran.** `scripts/intro_to_graph.py`, a graph of two steps
(`search`, then `write`) over a state with `question`, `chunks` and `answer`. It runs
with `python scripts/intro_to_graph.py` and printed exactly what it should:

```
{'question': 'why do results differ?', 'chunks': [...], 'answer': '... I read 2 chunks'}   <- invoke
{'search': {'chunks': [...]}}                                                              <- stream
{'write': {'answer': '...'}}                                                               <- stream
```

(The user's own copy is `scripts/intro_to_graph.py`. A reference copy is in the
git-ignored `artifacts/lesson1_graph.py`.) The first run failed with
`ImportError: cannot import name 'End'`. Cause: `START` and `END` are ALL CAPITALS in
LangGraph. The user fixed it alone.

**What the user now knows** (do not re-teach):

- A **state** is one dictionary (a `TypedDict` with fixed keys) that goes from step to
  step. A **node** is one function. An **edge** is an arrow between two nodes.
  `compile()` builds the graph, `invoke` runs it, `stream(stream_mode="updates")` shows
  each step.
- A node **receives the WHOLE state** and **returns ONLY what it changed**. LangGraph,
  not the node, puts the change into the state.
- The graph is **fixed** (all nodes and edges are written down). A conditional edge
  decides which path to walk at run time. The graph is not "dynamic" in the sense that
  nodes appear by themselves.
- A new key later means a **new line in the `State` class**. A key that is not in
  `State` is **silently ignored** by LangGraph (a typo trap).
- Parallel steps that write the same key without a reducer raise `InvalidUpdateError`.
  This was only mentioned, not taught: it is lesson 2.

**The three check questions, and what the user answered** (the answers were loose, and
this is what was corrected, so do not repeat the same mistakes):

1. *Why can `write` read `question` when `search` did not return it?* The user said
   "its own LangGraph mechanism". Correct: LangGraph keeps the whole state, and nothing
   replaced `question`.
2. *What is `answer` if `write` returns `{}`?* The user did NOT give a value. Correct:
   `""`, the value from the start. There is no error and no warning, so we must test the
   output of each step.
3. *Which variables go in the state?* The user said "variables that change in every
   node", and wrote `threat_id`. **Corrected:** the rule is "put in the state what a
   LATER STEP or a LATER TURN must read". And **`thread_id` is NOT in the state**: it is
   the name of the chat and goes in the call,
   `graph.invoke(start, config={"configurable": {"thread_id": "chat-7"}})`. Keep OUT of
   the state: the database connection, API keys, and the full prompt (see 17.4). The user
   did understand that the saved state goes to the database, and that only what is in the
   state gets saved.

**Open mix-up to watch:** the user mixes up `thread_id` and the state. It is taught
properly in lesson 3. If it appears again before that, fix it in one sentence.

**Lesson 2 must teach** (a list that grows, with a reducer):

1. Why two steps writing the same key lose data: by default the second write REPLACES
   the first. Use a tiny real example with two steps that each return one finding.
2. A **reducer** is the rule for how a new value joins the old one. The default is
   replace. For a list that must grow, `Annotated[list[str], operator.add]`.
3. The user already asked, and was answered: a reducer matters for steps that run in
   parallel and also for a list that grows over a chain. In a chain, two replaces are
   fine. If you want to keep both values, you need a reducer.
4. Show the two outputs side by side (no reducer: `InvalidUpdateError` in parallel, or a
   lost value in a chain; with a reducer: both kept). Parallel order is NOT guaranteed.
5. Connect it to LabPilot: `findings` and `history` are the keys that grow (17.4).

Then the user types about 15 to 40 lines, says "done", Claude runs the checks, and every
file gets its own commit.

**The rules that apply to every lesson here** (the user asked for them again on
2026-10-07): follow the teaching order in "Format for every new concept" for a LESSON,
but answer a side question in plain short words, with no lesson structure. Never put a
one-line definition at the top of a reply. Explain every agent word inside the sentence
where it appears. About one screen.

**Other open items from this session:**

- The big repository as side A (now slice 12) is recorded in section 18, and its newest plan (parts of one fixed size, a round-robin join) is in section 23 (D68, D69). Nothing is built.
- **EmbeddingGemma 2** (740M parameters, open weights): the Gemma releases page on
  Google lists it with the date 2026-10-06. It is NOT in our embedder list and is not
  scored. Our rule is: a new embedder joins `MIGRATION` only after we score it on the
  fixtures. It was not found in the Gemini API model list, and it is not known whether
  AI Studio offers it. Ask the user for the exact model name if they see it there.
- The user's file `scripts/intro_to_graph.py` is the user's learning file. **It IS
  committed** (commit `3ec8c45`, checked with `git ls-files` on 2026-10-08). This bullet
  used to say "ask before committing it".

#### 17.10 Lesson 2 was taught, 2026-10-08

**Status: DONE, 2026-10-08.** The user typed `scripts/graph_with_reducer.py` (38 lines, both
graphs in one file; the name is not the `lesson2_reducer.py` planned earlier), ran the three
steps and pasted the outputs. Claude ran the file, `ruff check` and `ruff format --check`
(both pass), and tried the case the outputs did not show: the parallel graph WITHOUT the
reducer, on a copy. It stops with `InvalidUpdateError: At key 'findings': Can receive only
one value per step. Use an Annotated key to handle multiple values.` Both check questions
were answered (below). The file is committed on its own.

**The lesson had to be redone once.** The first version mixed the four parts, had no math,
and showed no real state before and after each node. The user said "you forgot the
teaching structure". The rule, again: a lesson has the four labelled parts (concept,
details, math with every symbol defined, where it sits in the pipeline), and it shows the
real state dict after each node.

**The exercise, three steps:**

1. Two nodes one after the other, both returning `findings`, with `findings: list[str]`.
   Run it: only the `lr` finding is left, and there is no error.
2. Change the key to `Annotated[list[str], operator.add]` (add `import operator` and
   import `Annotated`). Run it: both findings.
3. Bonus: make both nodes start from `START` and end at `END` (parallel). With the reducer
   both findings are kept. Without it: `InvalidUpdateError`.

**What the user now knows** (do not re-teach):

- The default rule is **replace**: `s_{t+1} = u_t`, so only the last value is left.
- A **reducer** is any function `(old, new) -> result`. `operator.add` joins lists, so
  `s_n = s_0 + u_1 + ... + u_n`. A reducer can also keep ONE value, for example `max`.
  For parallel nodes, a reducer whose result does not depend on the order is safer.
- `Annotated[type, extra]`: Python ignores `extra`, and LangGraph reads it. It is the same
  idea as FastAPI's `Annotated[str, Query(max_length=50)]`. A function in the extra item
  is used as the reducer. No extra item means replace.
- With a reducer, a node returns **only its new items**.
- Two nodes writing the same key in the same step, without a reducer: `InvalidUpdateError`.
- Different keys can use different rules: `findings` uses add, `tries` (the retry counter)
  uses the default replace.
- The user's answer to the check question "`verify` runs 14 times, what is in `findings`?":
  default rule -> only the last one; `operator.add` -> 14. **Corrected:** with add the count
  is the SUM of what the runs return (a run may return 0 or 2 items), and in a parallel
  run the default rule gives an error, not "the last one".

**The two check questions are ANSWERED.** (1) Why is there no error in step 1 when a finding
is lost? The user said "because it is replaced, but in parallel it must keep both and it
can't". Right idea, small fix: LangGraph does not try to keep both. The rule "replace" needs
one winner. In a chain there is one write per step, so the last write wins. In parallel two
writes arrive in the same step, there is no winner, so it stops with an error. (2) What do you
see if `check_lr` returns `state["findings"] + [...]` while the reducer is on? The user said
"all we have plus this extra words in the middle". Claude ran it on a copy:
`['CLIP_NORM...', 'CLIP_NORM...', 'lr...']`, so the old item appears **twice** (the node gave
back old + new, and the reducer added that to the old again). With a reducer a node returns
only its new items. In the parallel graph the order of the two findings is not guaranteed; in
the user's runs `CLIP_NORM` came first both times.

**Side questions answered in this session, do not re-teach:** `extract_claims` is one model
call over A, then a search and a `verify` per claim (the cost plan allows 5 claims per
`verify` call, so 14 claims need 3 calls); node versus tool versus capability (19.2);
where ReAct is used (19.1); how the planner chooses a plan (19.5); `summarize` runs in the
two-file case even when nobody asked (19.6).

**The user's confusion about function calling.** Over about ten messages the user kept
reading "function calling" as "we send arguments TO the model". It is the other direction:
the model WRITES a function name and arguments in its answer, it never runs anything, and
our code reads them (19.2). It ended with the user saying they were dazed. **Decision D34:**
function calling gets its own small lesson before slice 4, where the user runs a real
request and sees the request and the answer. Until then, answer in ONE sentence only.

**The "dazed" rule.** When the user says they are confused or dazed, STOP adding ideas. Give
one sentence, park the topic, and return to the exercise. Too many new ideas in a row was
the cause every time.

#### 17.11 Lesson 3 was taught, 2026-10-08

**Status: taught on 2026-10-08 and DONE on 2026-10-09.** The user typed `scripts/graph_with_memory.py` (not the planned name
`lesson3_memory.py`), ran it, and it was committed alone (`df1331e`, `ruff check` and
`ruff format --check` pass). The output was right: call 2 says `seen 1`, call 3 says `seen 0`
(chat-8 is a new thread), and `get_state(chat7)` holds both questions. The user printed the whole
`StateSnapshot` (no `.values`), which also shows a `checkpoint_id` per saved copy and a
`parent_config` that points to the previous copy: that is the list D22 will have to trim.

**What went wrong in the user's first run, and what was taught from it** (do not re-teach):

- Their `State` still had the key `findings`, copied from lesson 2, while the node read
  `state["history"]` -> `KeyError: 'history'`. Their second mistake: `"history": [state["history"]]`
  where it must be `[state["question"]]`. They fixed both alone after one message.
- **Input is a partial state.** `invoke` does not need every key. LangGraph merges the input into
  the saved copy of the thread. Lessons 1 and 2 sent every key only for clarity, not because it is
  required (tested: lesson 1 works with only `question`, lesson 2 works with `{}`). A `TypedDict`
  is not checked when the program runs; only a type checker such as mypy looks at it.
- **The rule for reading a key:** a node can read a key only if the key has a value at that
  moment. A key gets a value from four places: (1) the input we send, (2) an earlier node, (3) the
  saved copy of the chat, (4) a reducer, which starts the key as an empty value of its type
  (`[]` for `list[str]`). If none applies: `KeyError` (tested with `chunks` and with `history`
  without the reducer). **I first stated this rule with only three places and the user caught the
  hole** (call 1 reads `history` that nobody sent). Check a rule against the exercise before teaching it.
- **`config` is not state.** `thread_id` tells LangGraph which saved copy to load, like
  `WHERE chat_id = 'chat-7'` tells Postgres which row to read. It is not a column of the row.

**What was taught** (the four labelled parts: concept, details, math, where it sits):

- Until now the state lived only during one `invoke`. A **checkpointer** saves a copy of the
  state after every node (like `torch.save`, but automatic). A **`thread_id`** is the name of
  one chat (like a primary key). The same name loads the latest saved copy; a new name starts
  empty.
- `compile(checkpointer=...)` turns saving on. `thread_id` is NOT a key of `State`: it goes
  in `config={"configurable": {"thread_id": "chat-7"}}`. (The user mixed these up in lesson
  1, see 17.9.)
- At the start of a call LangGraph loads the latest copy of that thread, then applies the new
  input with the SAME rules from lesson 2 (`question` replaces, `history` adds).
- The math: `s^c_t = run(r(s^c_{t-1}, u_t))` and `s^c_0 = empty`. `c` is the `thread_id`, `t`
  the message number, `s` the saved state, `u` the new input, `r` the rule of each key.
  Different `c` never mix.
- Today `InMemorySaver` (the copies live inside the Python process and are lost on restart).
  Later the Postgres saver in the same Supabase database (D19, lesson 4).

**The exercise.** State: `question: str`, `history: Annotated[list[str], operator.add]`,
`answer: str`. One node `respond` returns `answer` (it says how many earlier questions it has
seen) and `history: [state["question"]]`. Compile with `InMemorySaver()` from
`langgraph.checkpoint.memory`. Calls 1 and 2 use `thread_id` `chat-7`, call 3 uses `chat-8`,
then print `graph.get_state(chat7).values`. Claude ran a reference copy (it is not in the
repo): the answers say "seen 0", "seen 1" and "seen 0", and `history` of chat-7 holds both
questions. `history` needs no initial value when the key has a reducer. Claude's reference
file passes `ruff check` and `ruff format --check`.

**Next, lesson 4:** cut `ask()` into steps that receive their functions from `api/` (D7), swap
the in-memory saver for the Postgres saver, and add `thread_id` to the compare request and
response (D17). Before that, check `langgraph-checkpoint-postgres` (D19: package name and
version, works with `psycopg 3.2.12`, works on the session pooler at port 5432) and how to
keep only the latest copy of each chat (D22).

#### 17.12 Lesson 4 was started, 2026-10-11

**Status: part 1 of 3 DONE (taught and run on 2026-10-11). Part 2 is DONE too (17.13). Part 3 is
DONE too (17.14).** Lesson 4 was split into three parts so each
one stays short: (1) the nodes get their functions from outside, as a small
script; (2) `ask()` is cut into nodes, the first change inside `labpilot/`;
(3) the Postgres saver, `thread_id` in the API, one measured chat and the
cleanup of D35.

**Part 1, what was taught.** A node must not import the database or a model (the
layer test forbids it for `agent/`), so `build_graph(search, generate)` receives
the two functions and builds the graph. The node functions are written INSIDE
it, so they can use `search` and `generate`: an inner function that uses a
variable of the function around it is a **closure**. LangGraph calls a node with
only the state, so a second argument is not possible. A class with `self.search`
does the same job and was shown beside it. The closure was chosen because it is
shorter and the project rule says not to use a class only to group functions. In
part 2 it may become a class or a small dataclass of tools, because the real
`ask()` needs about six. Claude ran a reference copy first (it is not in the
repo), and the output is:

```
{'question': 'why do results differ?', 'chunks': ['chunk about learning rate', 'chunk about clipping'], 'answer': 'why do results differ? -> I read 2 chunks'}
```

**What the user did not understand, and what worked.** The first explanation put
"closure", "inner function" and "variables of the function around it" in one
sentence, and it failed. Four more messages were needed. What worked: a
`make_greeter(name)` example called twice (`say_amir`, `say_sara`, each remembers
its own name); the sentence "a function that remembers variables from outside
itself"; and `return greet` (the function) against `return greet()` (its
result). The user then restated it correctly: *a function inside a function that
uses the outer function's argument is a closure.* **A gap to name when it
appears: in Python a function is a value** (it can be put in a variable, passed
and returned), and `return greet` without brackets does not run it.

**The saved copies, answers to the user's questions.**
- Each saved copy is the WHOLE state at that moment, not only the change. The
  newest copy already holds everything older copies had in the growing keys
  (`history`, `findings`). Message 3 starts from the copy at the end of message 2.
- By default the saver adds a NEW ROW for every step and replaces nothing, so a
  chat leaves many copies. At the start of message 2 the copy still holds message
  1's `answer` until the answer step replaces it (an earlier example wrongly
  showed it empty).
- Anything needed from an old message must live in a growing key. It cannot
  rely on an old copy staying in the database.
- The frontend: only the `thread_id` is decided. Showing the old messages after
  a refresh needs a route that reads the history, which is NOT designed (Step 3).

**Part 1 was RUN and CHECKED, 2026-10-11.** The user typed `scripts/graph_with_tools.py`
(37 lines) on `feat/agent-nodes`. Claude ran it with Python 3.13.14, and `ruff check` and
`ruff format --check` pass. The output is right:
`{'question': 'why do results differ', 'chunks': ['chunk about learning rate', 'chunk about clipping'], 'answer': 'why do results differ -> I read 2 chunks'}`.
The user named the fake `fake_answer` while the parameter is `generate`; that works and was
left alone. It was committed the same evening: `4fb6b48` on `feat/agent-nodes` and `5cb6388`
on `main` (same content, two hashes).

The two check questions of part 1, and the answers:

1. *Where does the name `search` in `search_node` come from?* The user: "its closure rule,
   inner function can use outer function arg". Correct.
2. *You want a search that returns 3 chunks. What changes?* The user: "only need to change
   `search_node` to return three chunks". **Wrong, and it is a habit to watch.** Nodes never
   change. Write a new function `search_three` and call `build_graph(search_three,
   fake_answer)`. The first graph keeps its own function (like `say_amir` and `say_sara`).
   In the real app `search_node` stays the same: `api/` passes the real database search and
   a test passes a fake one. Search code inside the node would also break D7. Watch for
   this again in part 2, where the nodes are real.

The user stopped here for the day ("that enough for today").

**D19 was CHECKED, which was the planned first job of slice 2.**
`pip install --dry-run langgraph-checkpoint-postgres` would add TWO packages,
`langgraph-checkpoint-postgres 3.1.2` and `psycopg-pool 3.3.3`. It requires
`langgraph-checkpoint>=4.1.0,<5.0.0` (we have 4.2.0) and `psycopg>=3.2.0` (we have
3.2.12). **Nothing is installed.** What follows was read from the library's source
on GitHub `main`, NOT yet from the 3.1.2 install: `PostgresSaver.from_conn_string`
is a context manager that opens its own connection with `autocommit=True`,
`prepare_threshold=0` (no prepared statements, so the session pooler is safe) and
`row_factory=dict_row`. The docstrings do not say these are required, so a
connection we pass in should set the same. Its methods are `setup` (creates the
tables and runs migrations), `put`, `put_writes`, `get_tuple`, `list`,
`delete_thread` (a WHOLE chat) and `get_delta_channel_history`. **There is no
"keep only the latest copy" method.** The file also imports a class named
`ShallowPostgresSaver`. Its name suggests it keeps only the newest copy, but that
is NOT verified. Check both after the install.

**D35 was decided** (17.3): the cleanup of old copies runs right after each
message finishes.

**Branch.** `main` holds the lesson 3 script. The LiteRouter work (section 20) was
re-committed onto `main` by the user on 2026-10-11. The user made the branch
`feat/agent-nodes` (checked with git: the same commit as `main`, `fadc5c2`) and wrote
the part 1 script there. Part 2 goes on this branch. A new branch always needs the
user's permission.

**Checked again on 2026-10-12.** `main` = `origin/main` = `5cb6388`, and `main` is the
checked-out branch. `feat/agent-nodes` = `origin/feat/agent-nodes` = `4fb6b48`. The two share
`fadc5c2`. `scripts/graph_with_tools.py` is identical on both. `main` also holds the docs
commits `4a34fa3` and `d59ea4e`, which `feat/agent-nodes` does not. Which branch part 2 is
written on is the user's choice, and Claude does not create a branch without asking.

**Open, for the user to decide:** how to delete the old copies (our own SQL,
`ShallowPostgresSaver`, or keep all copies and delete whole old chats later), and
the shape of part 2 (closure, class, or a small dataclass of tools). The second one was
DECIDED in part 2: a closure, see 17.13.

#### 17.13 Lesson 4, part 2 was done, 2026-10-12

**Status: DONE, 2026-10-12.** The user typed every line of product code. The tests were given for
copy and paste (the user's rule, below). `ruff check .` and `ruff format --check .` pass (259 files).
The full suite is **1113 passed, 115 skipped** of 1228 tests: 110 of the skips are smoke tests that need
`--run-smoke`, 5 skip by their own rule, and the 83 database tests ran. The work is committed on
`feat/agent-nodes`: `74fb3b6` (the toy script `graph_with_branch.py` and docs) and `b1f4ba3` (graph, tests,
wiring), both pushed. Part 3 was done later (17.14).

**Part 2 had two steps.**

- *2a, the new idea, as a toy: `scripts/graph_with_branch.py`.* A **conditional edge** is an arrow whose
  end is chosen by a small function while the graph runs. The node `check` writes `fits`; `pick(state)` reads
  it and returns the NAME of the next node as text. `pick` is not a node: it writes nothing and does not
  appear in `stream`. Both branches write `chunks` and go to `answer`; only one runs per call, so lesson 2's
  `InvalidUpdateError` cannot happen. Three QUIET failures were run and seen: a missing arrow (`stuff` to
  `answer`) ends the run after `stuff` with no error and `answer` is simply absent from the final state; a typo
  in the name `pick` returns ends the run with only a log line; and a node that reads a key nobody wrote fails
  LOUD (`KeyError: 'size'`, the lesson 3 rule: the user forgot to send `size` in the input). The user added an
  `empty` path for blank questions and learned two things: use `.strip()` (a question of spaces is not empty),
  and the blank path cannot go to `answer`, because `answer_node` reads `chunks` and nobody wrote it there.
- *2b, the real graph.* `labpilot/agent/graph.py`: `State` (10 keys),
  `build_graph(*, measure, fits, stuff, search, make_prompt, generate) -> CompiledStateGraph`, five nodes
  (`measure`, `stuff`, `search`, `prompt`, `generate`) and one conditional edge. Fully typed (the first version
  had no hints; the project rule is full hints on public functions, so it was corrected).
  `agent/__init__.py` exports `State` and `build_graph`. In `api/services.py`, `ask()` keeps its docstring and
  its blank-question check, then runs `_ask_graph(conn, client).invoke({"question", "a", "b"})` and builds the
  same `Comparison` from five state keys. `_ask_graph` builds the graph on every call and hands it six real
  functions: `partial(_sides, conn)`, `fits`, `stuff_sides`, `search_sides`, `make_prompt`, `generate`.
  **`stuff` and `search` have one shape**, `(sides, question) -> (chunks, totals)`; `totals` is `None` when
  everything was read.

**Decisions of part 2:**

1. **Closure, not class.** Shorter, and nothing has to be remembered between calls. The honest cost: a node
   cannot be tested alone, only the whole graph. Revisit when `build_graph` has about 10 nodes (slices 5 and
   6): then a class, or a dataclass that holds the functions. Only the inside of `agent/` would change.
   **Superseded on 2026-10-15 for every new node: one file per node, see D45 and the Working Rules.**
2. **`sides` and `result` are typed `Any`**, because `agent/` may not import `store/` or `llm/` (layer test).
   The graph only carries them.
3. **The blank-question check stays in `ask()`, once, at the door** (before any database read or model call).
   `InvalidQuestion` is an API type. Core code trusts its input. A second door into the graph needs the check
   too, as ONE shared function and never as a copy.
4. **Errors are converted in `api/`**, inside the `generate` function handed to the graph
   (`AllFreeTiersExhausted` to `GenerationUnavailable`). The graph passes errors through unchanged, which a
   test proves for three stages. So the 404, 409 and 503 mapping did not change.
5. **Names:** a helper used by one file starts with `_` (`_ask_graph`), and outside code imports from the
   package front door (`from labpilot.agent import build_graph`). The user first wrote `ask_graph` (3 tests
   failed with one message) and imported from `labpilot.agent.graph`. The first was fixed; **the second was
   still in `services.py` when this was written** and works.

**Tests (12 new).** `tests/unit/agent/test_graph.py` (9, with fake functions, including one parametrized
test that an error from `measure`, `search` or `generate` reaches the caller unchanged) and
`tests/api/test_ask_graph.py` (3: `ask()` runs the graph and builds `Comparison` from its state, and a blank
question is refused before the graph is built). **Eight deliberate breaks** were run on a temp copy of the
repo, each caught: an inverted `pick` (7 tests), search losing `totals` (1), stuff forgetting `totals` (4),
`generate` swallowing its error (1), `measure` args swapped (1), the arrow `stuff` to `prompt` forgotten (3),
`ask()` dropping `totals` (1), the blank check deleted (2). Unit and API went from 999 to 1011 (+12), then
1113 in the full run (it includes the database tests).

**Open, for part 3.** The state now holds whole objects (`sides` from `store/`, `Chunk` tuples, the
`LLMResult`), while D20 says the state should keep chunk ids and not text. The Postgres saver must turn the
state into bytes. Whether it accepts these objects is NOT known and must be measured first in part 3,
together with the size of one real chat (17.5). The graph is built again on every `ask()`; its cost alone was
not timed (the 12 new tests run in 0.06 s). **Answered in 17.14:** the saver accepts the objects if their five classes
are on an allowlist (D37), one real chat is about 160 KB, and building the graph takes 1.7 ms.

**Process rules the user set on 2026-10-12.** (1) The user types ALL product code; only tests are
copy-paste. Claude never edits repo files. A temp copy for checking is allowed, but Claude says so first (the
user stopped a session when edits at repo-looking temp paths looked like a broken rule). (2) A step is given
WHOLE in one message: code, tests, wiring, commands and the answers to Claude's own check questions. No new
"2a, 2b, 2b-1" splits. This overrides the line "about one screen, split and ask" in the banner at the top of
this file for the size of a build step; the words stay simple (B1-B2).

#### 17.14 Lesson 4, part 3 was done, and slice 2 is CLOSED — 2026-10-13 and 2026-10-14

**Status: DONE.** The user typed the part 3 code on 2026-10-13 (branch `feat/agent-nodes`, `9bc94c6` and
`15d398a`). On 2026-10-14 Claude ran a closing review of the whole slice (parts 1 to 3), added the tests it
found missing, and replayed everything onto `main`, one file per commit (the user asked for this). **Slice 2
is closed. Slice 3 is next.** `feat/agent-nodes` is kept.

**What part 3 built** (all of it is on `main` now):

- `labpilot/api/checkpoints.py`: `SAVED_TYPES`, `SERDE` (D37), the `PRUNE` query, `open_saver(conn)` and
  `prune(conn, thread_id)`. It sits in `api/` because it needs `llm/` and `store/` classes.
- `labpilot/agent/graph.py`: `State` has `history: Annotated[list[str], operator.add]`. A last node
  `remember` appends the question. `build_graph(..., checkpointer=None)` passes the saver to `compile()`.
  **Nothing reads `history` yet.** The first reader will be the node that rewrites a follow-up question
  (D5, slice 6).
- `ask(..., thread_id=None)` in `api/services.py`. Without an id nothing changes. With one: the graph gets
  the Postgres saver, runs with `durability="exit"` (D36), and `_forget_old_copies` runs `PRUNE` afterwards.
  A prune failure is only logged (D35). The unused helper `_cut` was deleted at the same time.
- `POST /compare` (D38), `schemas.py` (`thread_id` optional in the request, required in the reply),
  `connect(url=None, *, autocommit=False)` in `store/connection.py`, and `web/app.js`.
- `scripts/setup/setup_checkpoints.py` creates the four tables once: `checkpoints`, `checkpoint_blobs`,
  `checkpoint_writes`, `checkpoint_migrations`. **Run it from the repository root as
  `python -m scripts.setup.setup_checkpoints`.** `python scripts/setup/setup_checkpoints.py` fails with
  `ModuleNotFoundError`, because Python then puts the script's folder on the path and not the repository
  root. It needs an autocommit connection, because the library builds three indexes with
  `CREATE INDEX CONCURRENTLY`. It was run once on the real database (the tables are in `public`). Tests get
  the same tables in their own throwaway schema from the fixture `chat_tables` (about 12 s per test module).
  Since 2026-10-14 the script also locks the four tables with row level security (17.15).
- `requirements.txt`: `langgraph-checkpoint-postgres==3.1.2` (it also brings `psycopg-pool`; about 1.4 MB
  together) and `langgraph-checkpoint==4.2.0` (see the review below).

**What the saved rows are, in plain words.** A *checkpoint* row is one saved copy of the state. A *blob*
row holds the bytes of ONE state key at ONE version (a *channel* is a state key, plus a few internal ones).
Small values (a string, a short list) are written inside the checkpoint row itself, and big objects are
written as blobs. A *write* row is a pending write of a step that has not been saved as a copy yet. `PRUNE`
keeps the newest copy of the chat, deletes the older copies and their writes, and deletes every blob that the
newest copy does not point to. The newest copy points to its blobs through `channel_versions` (a JSON object
`{key: version}` inside the checkpoint row). `checkpoint_ns = ''` means the main graph; subgraphs would have
another namespace, and `PRUNE` assumes there are none.

**Measured on 2026-10-13** with a fake model function and the real Supabase database through the VPN, one
chat: with the default saving, 6 copies (~460 KB) and 4.5 to 6.5 s per message; with `durability="exit"` and
the prune, a steady 1 checkpoint and 4 blobs (~160 KB) and about 1 s per message. At ~160 KB per chat, 500 MB
holds at most about 3,100 chats, **but only if nothing else used the space, and the artifacts are the big
users (17.6)**. `build_graph()` takes 1.7 ms. **A chat with a real model was NOT measured.**

**The closing review, 2026-10-14.** Claude read the whole system (parts 1 to 3 and the code around them) and
ran 33 deliberate breaks on throwaway copies, each in one line. Most were caught. What was NOT caught:

- **Five real gaps in the `PRUNE` query.** It has 13 breaks (C5 to C17). Seven were caught by the earlier
  tests. Six survived: C9 (the writes rule deletes the newest copy's writes), C10 (the writes rule has no
  chat filter), C11 (the writes rule deletes nothing), C15 (a blob is matched by version only and not by
  channel), C16 (the newest copy is picked among ALL chats), and C17 (no `checkpoint_ns` filter). **C17 is an
  equivalent break**: it changes nothing today, because the graph has no subgraphs. The other five are real.
- **The page.** Deleting the line that sends `thread_id` (J1), or the line that saves the id from the reply
  (J2), left the whole suite green. The server then makes a new chat for every message and the page looks
  fine.
- **A missing pin.** `labpilot` imports `langgraph.checkpoint.*`, which is shipped by `langgraph-checkpoint`,
  a different package from `langgraph`. It was not in `requirements.txt` (it only arrived through another
  package). The old pin test read the first word of an import (`langgraph`), so it was happy.
- **Two gaps found by reading the system:** the length of the report could be lost on the way to the
  provider (S1), and a node in `agent/` could import `requests` or `psycopg` and still pass the layer test
  (X1, X2: D7 is about functions handed in from outside). A third idea, that the stuffed path could invent
  totals (S6x), was checked and is NOT a gap (see below).

**11 new tests** (each one was shown to pass on clean code AND to fail when its own break is made):

| file | tests | what they guard |
|---|---|---|
| `tests/integration/test_prune.py` (new) | 6 | one rule of `PRUNE` each, on rows inserted by hand: only the newest copy stays; the writes of old copies go and the newest writes stay; an old blob that the newest copy points to stays; a blob only an old copy points to goes; another chat is never touched even when its ids are newer; the newest copy is chosen among the chat's own copies |
| `tests/unit/test_frontend_contract.py` | 2 | the page sends every field of the compare request, and reads `thread_id` from the reply |
| `tests/unit/test_packaging.py` | 1 | every module `labpilot` imports comes from a package that is pinned. It maps each dotted import to the installed package that ships it, using the file lists in the package metadata. It found the missing pin |
| `tests/unit/test_architecture.py` | 1 | `agent/` imports none of: `requests`, `httpx`, `aiohttp`, `psycopg`, `psycopg_pool`, `socket`, `subprocess`, `urllib`, `urllib3` |
| `tests/integration/test_api_over_the_chain.py` | 1 | the request that reaches the provider asks for `REPORT_MAX_TOKENS` |

Before the review the part 3 work had its own tests too (savers, route, graph history, four database tests
for chat memory, the connection flag). The full suite on `main` after all of it: 1151 passed, 115 skipped (almost all smoke tests that need `--run-smoke`). **Two of the review ideas were checked on a copy of the repo from before their test existed.** S1 (the report length dropped): the break passed unit, api and integration (1139 passed), so it was a real gap. S6x (an invented total on the stuffed path): NOT a gap, because six older tests in `test_api_over_the_chain.py` already fail on it (they check the chunk counts in the reply). The test written for it was removed again (`ab1cb9e`), which is why this section says 11 new tests and not 12.

**Known limits. None of them is fixed.**

- If the chat tables do not exist in the database, `/compare` answers with a 500, not with a clean error.
  Run the setup script first.
- `PRUNE` assumes no subgraphs (`checkpoint_ns = ''`). Add the filter back if a subgraph is ever used.
- The server does not limit the length of the `thread_id` it receives.
- A chat that nobody uses again is never deleted (the same problem as the artifacts, D23).
- Anyone who knows a chat id can read and continue that chat. There is no login.
- The page has no "new chat" button. To start a new chat, clear `labpilot.thread` in the browser.
- A chat with a real model was not measured (only a fake function).
- `history` is saved and not read by any node yet.

**Process notes.** (1) The user's editor kept an old copy of `services.py` open and overwrote a fix with it.
Close the old tab with "Don't Save", reopen the file, and check the line. (2) A mutation sweep that ran while
the network was down gave "caught" verdicts that were only connection errors. A result that is only `ERROR`
and has no `FAILED` line is not a result; it was run again with `-rfE`. (3) A `git checkout` is never used to
undo a break (it restores to the last commit, not to the state before the break); the breaks ran on copies.
(4) The replay onto `main` was one file per commit, with the suite green at each commit except for two short
windows where a file and its test depend on each other (the `ask()` change and `test_ask_graph.py`, and the
route with `schemas.py` and `test_compare.py`). Their commit messages say so. (5) Two commit messages on
`main` are wrong, and they were not rewritten (history on `main` is not rewritten). The message of
`test_prune.py` says "ten of the sixteen mutations of the query survived the earlier tests"; the right
figures are above (6 of 13 survived, five real and one equivalent). The message of the S6x test (`62248fa`)
says the break "broke nothing before this test"; that is false, and `ab1cb9e` removes the test and says
why. (6) **A claim in a commit message is checked before it is written.** Both wrong figures came from
memory, not from the logs.

#### 17.15 After slice 2 closed: the lock on the tables, and the examples folder — 2026-10-14

**Status: DONE and committed on `main` by the user: six commits on the night of 2026-10-14 (`d0492d4` to
`6a32137`, between 01:40 and 01:44). It is not a slice. Claude wrote it down afterwards, at the user's request.**

**Why the lock.** Supabase opens every table in the `public` schema to its own web API, and the roles `anon` and
`authenticated` get full rights on new tables. That is what the comment in `schema.sql` says; it was not checked
against Supabase's own pages in this session. *Row level security* (RLS) is a Postgres switch that works per table.
With RLS ON and no rule (a *policy*) written, those two roles see no rows. Our app connects as `postgres`, which
skips RLS, so the app should behave as before. These tables hold uploaded code and chat text, so they should not be
open to that API.

**What was built:**

| commit | change |
|---|---|
| `d0492d4` | `labpilot/api/checkpoints.py`: `CHAT_TABLES` (the four names) and `lock_tables(conn)`, which runs `alter table <name> enable row level security` for each one. The list is needed because the saver library creates the chat tables, not our `schema.sql`, so we lock them by name afterwards |
| `520470d` | `labpilot/store/schema.sql`: the same switch for `artifacts` and `chunks`. It runs every time `create_schema` runs, and repeating it changes nothing |
| `b6c6735` | `scripts/setup/setup_checkpoints.py` calls `lock_tables` after `setup()`, on the same autocommit connection |
| `88e217b` | `tests/integration/test_chat_tables.py`, 2 tests: the list names exactly the tables the saver creates (so a new table in a library update turns the test red), and `lock_tables` turns RLS on for all four |
| `d99e005` | `tests/unit/store/test_schema.py`, 1 test: it reads `schema.sql` and checks that every `create table` has a matching `enable row level security`. It also fails when the file creates no table at all, so it cannot pass on an empty read |
| `6a32137` | the five lesson scripts (`intro_to_graph.py`, `graph_with_reducer.py`, `graph_with_memory.py`, `graph_with_tools.py`, `graph_with_branch.py`) moved from `scripts/` to `examples/langgraph/`. Only the path changed. `scripts/setup/setup_checkpoints.py` stays in `scripts/`, because it is a real tool and not a lesson |

**Checked in this session (2026-10-14).** Unit and api tests: 1039 passed, 5 skipped. The three new tests: 3 passed
in 12.6 s against the real Supabase (in a throwaway schema), none skipped. The whole `tests/integration` folder
and the new unit test, run together: 116 passed, none skipped, in 236 s. Those tests build the tables from
`schema.sql` (RLS on) and the app code reads and writes them, so the app is not blocked by the lock.

**NOT checked.** (1) Mutation checks of the three new tests were not run, so it is not shown that each one fails
when its rule is broken. (2) Whether RLS is ON in the tables of the real project now. It is only on after
`create_schema` and `scripts.setup.setup_checkpoints` have been run against it, and nothing in the files says they were.
(3) That the app reads and writes fine with the lock is shown in a throwaway schema. It was not tried on the real
`public` tables, and that the web API (`anon`) really sees nothing was not tried at all.

**What the lock does NOT do.**

- It does not protect the app's own route. Anyone who knows an artifact id or a chat id can still use `/compare`,
  because there is no login (17.6, 17.14).
- It does not change how the app reads and writes, because the app connects as `postgres`.
- A new table needs the same switch. The unit test covers `schema.sql`. A table made by a library needs its name
  in `CHAT_TABLES`, and the integration test fails when the list and the library disagree.

**Paths.** Sections 17.9 to 17.13 say `scripts/intro_to_graph.py` and so on. Those files are in
`examples/langgraph/` now. The old text was not rewritten, because it tells what happened on those days.

**Branches.** `feat/agent-nodes` (`b72955a`) has the lock as ONE commit and still has the lesson scripts in
`scripts/`. It also has the docs commit `63a0381` (the reminder that better citations are owed at the end of
Step 2), which `main` does not have.
