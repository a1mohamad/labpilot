# The old front page of CLAUDE.md

[Docs home](../README.md)

# CLAUDE.md — LabPilot

Project instructions for Claude Code, and orientation for any human reader.
Read the two rule sections first — they change *how* everything below is done.

> ## ⛔ READ THIS FIRST. IT APPLIES TO EVERY REPLY, IN EVERY SESSION.
>
> **THE USER IS A BEGINNER IN AGENTS, GRAPHS, CHAINS, LANGGRAPH, LANGCHAIN, MCP,
> THE INSIDE OF RAG, AND FINE-TUNING. THEIR ENGLISH IS NOT PERFECT (B1-B2).**
> They know PyTorch, FastAPI, Docker and Postgres well. They do **not** know the
> agent part, and this project exists to teach it. Step 2 is all of it.
>
> ### Write the WHOLE reply for this reader, from the first word to the last.
>
> This is true for every message: lessons, plans, status reports, "ready"
> messages, error reports and questions. It is true in every session.
> **The user must never have to ask for it, and must never have to remind you
> when a new session starts. If they have to, you failed.** They have already
> asked more than once (2026-10-05 and 2026-10-06).
>
> ### NEVER write an opener line instead of doing the work.
>
> No "You are new to agents, so a quick word first: ...", no one-line
> definition at the top, no bold reminder sentence. **The user called this
> cheating (2026-10-06), and they are right.** One word explained at the top,
> followed by an expert reply, fixes nothing: the other twenty hard words stay.
>
> ### What to do instead
>
> 1. **Explain inside the reply, at the place where the idea is used.** The first
>    time an agent word appears, give its meaning in the same sentence, in common
>    words, and connect it to something they already know (a PyTorch checkpoint,
>    a FastAPI route, a Postgres row). Never a bare term.
> 2. **One tiny real example** beside every rule (a real state dict, a
>    three-node graph). A definition alone does not teach this.
> 3. **Common words and normal full sentences.** Keep "because", "so", "then".
>    No headline fragments, no metaphors, no idioms. Use the same word for the
>    same thing. See [Communication](../rules/teaching-and-communication.md#communication).
> 4. **Do not copy words from this file into a reply. Translate them.** This file
>    is full of expert words (checkpointer, reducer, injected callable, fan-out,
>    plan-and-execute) that the user does not know.
> 5. **Short: about one screen.** If the topic needs more, split it and ask
>    before you continue.
>
> ### Check before you send. All three answers must be "yes".
>
> - Is every agent word explained **in the body**, in plain words, where it first
>   appears?
> - Could a reader with B1 English understand every sentence the first time?
> - Is the reply about one screen long?
>
> The teaching order for a new idea is in
> [the teaching format](../rules/teaching-and-communication.md#format-for-every-new-concept--follow-this-order).

> **This file was compacted on 2026-10-08.** The Step 0 and Step 1 history was
> condensed (repeated status notes, per-run tables, superseded plans). Every
> decision, rule, lesson and number that still matters was kept, every heading
> that other notes link to was kept (a few small sub-headings were folded into
> their paragraphs), and a note marks each place where a later result overturned
> an earlier one.
> The **complete, uncompacted text** is [DETAILS.md](README.md), a copy of the previous
> CLAUDE.md (only the slice 2 lesson status was updated in it afterwards, on 2026-10-08).
> Read it when a detail here is too short.
