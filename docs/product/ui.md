# The user interface (Step 3)

[Docs home](../README.md)

### UI shape — Step 3, recorded now

Two **named** slots, not a generic file list. The names make the comparison
direction visible: "compare A to B" is clear, "compare these 3 files" is not.

```
┌──────────────────────────┬──────────────────────────────┐
│  A — the reference       │  B — the implementation      │
│  📄 paper.pdf · 42 chunks│   + add file / folder / link │
└──────────────────────────┴──────────────────────────────┘
        (chat history)
┌─────────────────────────────────────────────────────────┐
│ Compare these and explain why the results diverge.      │ ← prefilled
└─────────────────────────────────────────────────────────┘
```

- **Both slots start empty.** Files are the user's data — never guess them. Only
  the *prompt* is prefilled.
- **The default prompt changes with state** — three fixed, versioned strings:
  0 artifacts → *"Ask a question, or add files to compare."* ·
  1 → *"Summarize this and find likely bugs."* ·
  2 → *"Compare these and explain why the results diverge."*
- **After the first turn the slots collapse to a thin bar** and stay visible all
  session. The empty slot is a permanent, passive invitation.
- **Show the chunk count** after ingest (`✓ 42 chunks`) — it proves the file was
  really read.
- **Show which model answered** under each reply — required by the `LLMResult`
  rule, so the user can tell tier 1 from tier 6.
- **Every finding shows its source** (`train.py:42`, `§4.2`) — the citation rule.

**The agent asks for what it is missing.** This is the active half of the design,
and it means the user never has to read instructions first:

> **you:** now compare it with my code
> **LabPilot:** I need a second file to compare. Add your code in slot B ↑

Because each capability declares its artifact precondition, the agent knows
exactly what is absent. It never fails silently and never pretends.

#### Notes for Step 3 from slice 6 (2026-10-22)

The page of Steps 0 to 2 is throwaway. These are the limits it taught us, so the real page does not repeat them.

- **A chat and its files must be kept together on the SERVER, not in one browser.** The page keeps two global `localStorage` keys, `labpilot.thread` and `labpilot.artifacts`. They are not tied to each other: they are right only while there is one chat per browser, and the page has no "new chat" button. The saved chat already holds the last `a`, `b`, `history` and `last_answer`, so a route such as `GET /chats/{thread_id}` can give a page the files and the earlier messages in any browser, and a real "new chat" is then safe.
- **"Remove this file from the chat" means STOP SENDING ITS ID.** It does not delete the artifact. The server already accepts 0, 1 or 2 ids at every message and clears the summary of a file that is no longer sent (D62, 17.24). Replacing a file already works: a new upload takes the slot.
- **Deleting old artifacts (D23, 17.6) will make `404 unknown_artifact` normal.** The page already empties the slot and says "add it again". The real message should say that the file was removed to free space.
- **Show what the server did:** the rewritten question of a follow-up, which files an answer used, and `n of m` parts for each side (the last one exists).
- **The prefilled question follows the number of stored sides** (version 2 of the three fixed strings). Keep the rule that the box is never sent empty, because its text is also the search query.
- **Ids carry their side** (`A-...`, `B-...`), and `ask()` uses that to put a lone artifact in its own slot. If the id format changes, `_in_their_own_slots` changes with it.
- **Show the model's thinking LIVE, like ChatGPT, and never save it (the user's decision, 2026-11-23).** While an answer is being made, the page shows the thinking pieces as they arrive, in a block that folds away when the answer starts. The text is NOT stored: not in the database, not in the saved chat (`last_answer`, `history`) and not in a later prompt, because it can be long, the answer does not need it and it would fill the 500 MB database. After a refresh it is gone. Only the NUMBER of thinking tokens goes to the log, when the provider reports it. It needs the streaming of the model calls (built in the scratch copy on 2026-11-23, not tested, not in the repository) and the SSE channel to the page. Today `_stream.py` throws the thinking away, so it must hand the thinking pieces to a callback (Google sends them as parts with `thought: true`, because the request asks for `includeThoughts`; other providers use fields such as `reasoning`, or send none). Open: which of the parallel calls of one question to show (first idea: only the final answer, `respond`, with the step names for the others), and what to show when a provider hides its thinking (then only the step name). The thinking is shown as text of the model, not as a fact: it can be wrong, and it can differ from the answer.
- **A refresh while a question is on its way loses that answer.** The saved chat holds an answer only after the message has finished. Showing progress (SSE) and giving the page a way to ask for the answer of a message it sent belong together.
- **An "Optimize prompt" button (an idea of the user, 2026-10-22, D63).** It must work at turn 0, with no history and even with no file, so it needs its OWN small instruction: it clarifies and structures the question, and it does not resolve "it" or "the second one" (that is the job of the follow-up rewrite). It is a small new route that calls one cheap model and returns the new text; the page puts it in the box, so the person can edit it before sending. Showing the rewrite is also the safe form: today the follow-up rewrite is silent, and a wrong one is invisible. Rules: a question that is already good comes back unchanged; the prefilled default question needs no button; each click spends one call of a limited quota (use the cheap chain of slice 11); the saved history keeps ONE of the two questions (decide which, and show the rewritten one). Low priority: after chats kept on the server, "new chat" and the progress display (SSE).
