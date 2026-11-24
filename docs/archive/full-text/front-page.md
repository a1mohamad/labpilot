# Full text: CLAUDE.md — LabPilot

[Docs home](../../README.md)

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
>    same thing. See [Communication](../../rules/teaching-and-communication.md#communication).
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
> [the teaching format](../../rules/teaching-and-communication.md#format-for-every-new-concept--follow-this-order).

**Contents:** [Working Rules](../retired-rules.md#working-rules-read-first) · [**Network precondition**](../../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work) · [Overview](../../product/overview.md#project-overview) ·
[Status](../../status/history.md#current-status) · [Environment](../../development/environment.md#development-environment) ·
[Conventions](../../development/code-style-and-tests.md#conventions) · [**Mutation testing**](../../development/mutation-testing.md#mutation-testing--claudes-standing-job-and-it-runs-unasked) ·
[Architecture](../../architecture/stack.md#architecture--stack) ·
[LLM Serving](../../llm/chains.md#llm-serving--fallback-chain) · [The Three Chains](../../llm/chains.md#the-three-chains--restructured-2026-08-11) ·
**The five-way rule** ·
[**Real quota numbers**](../../llm/quotas-and-pools.md#the-real-free-tier-numbers--measured-2026-08-16-and-they-overturned-a-lot) ·
[Quota pools](../../llm/quotas-and-pools.md#a-pool-is-the-bucket-that-runs-out-not-the-api-key) ·
[Input limits](../../llm/quotas-and-pools.md#two-kinds-of-limit-and-they-are-not-the-same-thing) ·
[Reasoning shape](../../llm/failure-rules-and-limits.md#the-reasoning-content-shape--found-2026-08-16) ·
[Adjacency retired](../../llm/quotas-and-pools.md#why-the-adjacency-rule-was-retired--2026-08-16) ·
[**Model routing**](../../agent/design.md#model-routing--a-chain-per-task-not-a-model-per-task) ·
[Thinking presets](../../agent/design.md#thinking-level--a-user-preset-never-a-per-model-switch) ·
[**Why the fixes failed**](../../step0/prompt-experiments.md#the-prompt-fixes-were-measured-and-they-failed--2026-08-17) ·
[**Slice 4 DONE**](../../step0/slices-1-to-4.md#slice-4--done-2026-08-17) ·
[**Slice 5 DONE — Step 0 closed**](../../step0/slice-5-and-the-api.md#slice-5--done-2026-08-17) ·
[**STEP 1 — THE PLAN, 8 slices**](../../step1/plan.md#step-1--the-plan-recorded-2026-08-20) ·
[**Slice 3 — notebooks DONE**](../../step1/document-formats.md#slice-3-first-half---done-2026-08-29-a-notebook-becomes-cells) ·
[**Loaders take bytes DONE**](../../step1/document-formats.md#loaders-take-bytes--done-2026-08-30) ·
[**`.pdf` DONE — 24 papers**](../../step1/document-formats.md#pdf--done-2026-08-30-measured-on-24-real-papers) ·
[**`.docx` DONE — 18 files**](../../step1/document-formats.md#docx--done-2026-08-30-measured-on-18-real-word-files) ·
[**Languages + the overlap fix**](../../step1/document-formats.md#other-code-languages--done-2026-08-31-and-the-overlap-bug-they-exposed) ·
[**Slice 3 — the PDF theory**](../../step1/document-formats.md#slice-3-second-half--pdf-the-theory-recorded-2026-08-30) ·
[**SLICE 4 — the theory + schema**](../../step1/vector-store.md#slice-4--the-theory-recorded-2026-09-03) ·
[**SLICE 4 first half DONE — the store**](../../step1/vector-store.md#slice-4-first-half--done-2026-09-04-the-table-and-the-write-path) ·
[**SLICE 5 — the theory + BM25 by hand**](../../step1/keyword-search.md#slice-5--the-theory-recorded-2026-09-06) ·
[**The fixture is saturated**](../../step1/keyword-search.md#the-fixture-is-saturated-so-it-may-reject-and-may-not-confirm--2026-09-07) ·
[**SLICE 5 MEASURED — the decision**](../../step1/keyword-search.md#slice-5-measured--2026-09-07-vector-ships-wrrf-is-a-named-candidate) ·
[**SLICE 5 BUILT — the keyword half**](../../step1/keyword-search.md#slice-5--done-2026-09-08) ·
[**4 knobs, 3 lost fusion methods**](../../step1/keyword-search.md#the-four-hyperparameters-and-the-three-methods-that-were-lost--2026-09-07) ·
[**SLICE 6 — the theory + the reranking budget**](../../step1/reranking.md#slice-6--the-theory-recorded-2026-09-09) ·
[**SLICE 6 DONE — reranking HURT, and why that is a routing finding**](../../step1/reranking.md#slice-6--done-2026-09-11-built-measured-and-not-switched-on) ·
[**SLICE 7 — the decisions, and the one embedder list**](../../step1/ask-path.md#slice-7--the-decisions-taken-before-any-code-2026-09-13) ·
[**Quotas do not predict time — 6 embedders measured**](../../step1/ask-path.md#9-the-published-quota-does-not-predict-time--measured-2026-09-14) ·
[**The ask path — stuff, the N/2 rule, per side**](../../step1/ask-path.md#10-the-ask-path--decided-2026-09-14-before-piece-4-was-written) ·
[**The output budget — 9 decisions**](../../step1/ask-path.md#11-the-output-budget--nine-decisions-taken-2026-09-14) ·
[**The outline — step 2's ladder**](../../step1/ask-path.md#12-the-outline--build-step-2s-design-decided-2026-09-14) ·
[**The selector + scenario matrix**](../../step1/ask-path.md#13-the-selector-and-the-scenario-matrix-behind-it--decided-2026-09-14) ·
[**Steps 1-3 SHIPPED + the rerank window**](../../step1/ask-path.md#14-slice-7-build-steps-1-3-are-shipped--2026-09-14) ·
[**SLICE 7 COMPLETE — the ask path**](../../step1/ask-path.md#15-slice-7-is-complete--steps-4-5-and-6-2026-09-14) ·
[**SLICE 7 CLOSED — the review pass, 3 defects**](../../step1/ask-path.md#16-slice-7-is-closed--the-review-pass-2026-09-15) ·
[**Queries: generate, do not hardcode**](../../retrieval/design.md#the-fixed-checklist-is-domain-locked--corrected-2026-09-09) ·
[**Fan-out: 6 queries, 1 rerank**](../../retrieval/design.md#six-queries-one-rerank--the-half-this-section-was-missing) ·
[Why loaders take bytes](../../step1/document-formats.md#loaders-take-bytes--decided-2026-08-30) ·
[**Slice 1 DONE — the embedder**](../../step1/embedders-measured.md#slice-1--the-measurement-and-the-model-is-settled-2026-08-20) ·
[Slice 1b plan](../../step1/embedders-measured.md#slice-1b--more-embedders-and-why-it-moved-ahead-of-slice-2) ·
[Slice 1b — Google blocked](../../step1/embedders-measured.md#slice-1b--done-2026-08-20-and-google-is-blocked) ·
[**Slice 1b DONE — five embedders**](../../step1/embedders-measured.md#slice-1b-second-pass--five-embedders-and-cohere-is-the-surprise) ·
[Hybrid search](../../step1/embedders-measured.md#hybrid-search--decided-2026-08-20-built-in-slice-5) ·
[**Slice 8 decides embedder + reranker**](../../step1/plan.md#slice-8-decides-the-embedder-and-the-reranker--recorded-2026-08-28) ·
[**Hardening the API**](../../step0/slice-5-and-the-api.md#hardening-and-what-running-it-for-real-exposed--2026-08-17) ·
[**The API layout**](../../step0/slice-5-and-the-api.md#the-api-layout--restructured-2026-08-17) ·
[**The system-wide audit**](../../step0/slice-5-and-the-api.md#the-system-wide-audit--2026-08-17) ·
[**The page and the container**](../../step0/slice-5-and-the-api.md#the-page-and-the-container--2026-08-17) ·
[The test that could not fail](../../step0/slice-5-and-the-api.md#the-test-that-could-not-fail--2026-08-17) ·
[**THE ROOT CAUSE**](../../step0/prompt-experiments.md#the-root-cause-found-2026-08-17-session-10) ·
[**THE LEAN REWRITE**](../../step0/prompt-experiments.md#the-lean-rewrite-measured-2026-08-17-session-10) ·
[Multi-pass](../../step0/prompt-experiments.md#multi-pass-vary-the-model-not-the-seed-measured-2026-08-17) ·
[Archived checklists](../../step0/prompt-experiments.md#the-deleted-checklists-archived-for-step-2-and-not-for-the-prompt) ·
[New instructions](../../step0/prompt-experiments.md#what-the-new-instructions-must-ask) ·
[Instruction bugs](../../step0/prompt-experiments.md#the-instruction-bugs-found-by-experiment-2026-08-17) ·
[Thinking burn](../../step0/prompt-experiments.md#thinking-burn-high-is-not-better-measured-2026-08-17) ·
[**Prompt design rules**](../../step0/prompt-experiments.md#prompt-design-rules-earned-2026-08-17) ·
[**Cline — tier 1, free, zero credits**](../../llm/gateways.md#cline--the-eighth-platform-and-the-free-tier-that-costs-no-credits-2026-09-13) ·
[**The gateway sweep — Zen, Kilo, Requesty**](../../llm/gateways.md#the-gateway-sweep--zen-kilo-requesty-2026-09-19) ·
[**Qwen3.8-27B + DeepSeek V4 Flash**](../../llm/gateways.md#qwen38-27b-and-deepseek-v4-flash--added-to-the-chain-2026-09-19) ·
[**Reviving dead tiers — GLM-5.2, Cline**](../../llm/gateways.md#reviving-the-dead-tiers--investigated-2026-09-19) ·
[**Jev — a decision model, chain 3 tier 2**](../../llm/jev.md#jev--the-decision-model-and-the-first-paid-tier-2026-09-19) ·
[Model Ranking](../../llm/model-ranking.md#model-ranking--how-the-order-was-decided-2026-08-11) ·
[Platform Accounts](../../llm/platform-accounts.md#platform-accounts--verified-august-2026) ·
[Retrieval Design](../../retrieval/design.md#retrieval-design--recorded-2026-08-13) · [Chunking](../../retrieval/chunking.md#chunking--decided-2026-08-13-built-in-slice-3) ·
[Sample Pair](../../reference/sample-pair.md#the-sample-pair--quora_siamese-built-2026-08-14) ·
[Slice 3 Result](../../step0/slices-1-to-4.md#the-first-real-answer--measured-2026-08-14) ·
[Slice 4 Result](../../prompts/comparison-template.md#the-measurement--five-runs-all-saved) ·
[**Next: Coverage**](../../prompts/comparison-template.md#why-coverage-is-stuck--diagnosed-2026-08-14) ·
[Comparison Template](../../prompts/comparison-template.md#the-comparison-template--designed-2026-08-14) ·
[**STEP 2 — THE PLAN, 15 slices (0 to 14)**](../../step2/00-plan.md#step-2--the-plan-recorded-2026-09-22) ·
[**SLICE 10 REDESIGNED — no outcomes nodes, an ask-the-user pause**](../../step2/31a-slice-10-design.md#31-slice-10-redesigned--2026-11-12) ·
[**The daily chain update — end of Step 3**](../../step3/daily-chain-update.md#32-the-daily-update-of-the-chain-and-the-routes--an-idea-of-the-user-2026-11-18-for-the-end-of-step-3) ·
[Agent Design](../../agent/design.md#agent-design--step-2-recorded-2026-08-11) ·
[Build Plan](../../product/build-plan.md#build-plan--walking-skeleton) · [Fine-Tuning](../../step4/fine-tuning.md#fine-tuning-plan) ·
[Risks](../../product/open-risks.md#open-risks--revisit-before-or-during-the-build) ·
[Out of Scope](../../product/out-of-scope.md#explicitly-out-of-scope-for-v1)

