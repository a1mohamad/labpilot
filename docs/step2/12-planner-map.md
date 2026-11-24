# Section 12: the planner map

[Docs home](../README.md)

### 12. THE PLANNER MAP IS BUILT, AND ITS BUDGET WAS CORRECTED — 2026-09-28

*Built on `feat/planner-map` and fast-forwarded into `main`. **834 passed, 5
skipped** unit + api and the store integration tests green, measured BEFORE the
last change below (8,000 -> 12,000), which was committed WITHOUT a re-run at the
user's request - run the suite first thing next session.*

#### 12.1 What was built

```
store.read_headers(conn, id)       every chunk's header, source and lines.
                                   NO text, NO vector - one light read
store.file_scores(conn, id, q)     per file, the MAX cosine of its chunks to
                                   the question. MAX, not mean: a big file with
                                   one relevant chunk must not look unrelated
prompts.build_map(parts, scores=)  the planner's map of both sides
llm.KNOWN_DEAD                     dead tiers, KEPT at the tail of CHAIN
```

`file_scores` and `search` now share one guard, `_checked` - empty query,
unknown artifact, wrong model, wrong width - so the two cannot drift apart.

**`build_map` has three levels**, and only shrinks when it must:

```
1  it fits           every file, its classes/functions, their members.
                     No ranking - ranking a map that fits is cost, no benefit
2  too long          EVERY file gets one line; then details are given back to
                     the files closest to the question, in rank order. A file
                     too big to fit is SKIPPED, not the end of the loop
3  still too long    the rest are COUNTED by folder; the closest stay named
```

**No file ever disappears** - named or counted, always (D11: bias, never
filter). **The two sides share the budget** by the selector's rule: equal share,
and a small side's leftover flows to the other. Neither side is privileged.

Mutation-verified: **3 chain, 4 store and 8 map mutations, every one fires.**
Two survived first and were real gaps - a dead tier listed twice above the tail,
and a fixture with no split TOP-LEVEL function, where `part 1/2` sits exactly
where a member name would.

#### 12.2 The gateway work that rode along

```
LiteRouter   tier-1 GLM-5.3 Flash · DeepSeek V4 Flash · Qwen3.8 27B ·
             GLM-5.2 · Mistral Medium
OrcaRouter   GLM-5.3 Flash · DeepSeek V4 Flash
```

Seven tiers, one quota pool per gateway, `OPENROUTER_REASONING` on all of them
(GLM-5.3 returns EMPTY without it - reproduced on a third platform). **CHAIN was
47 tiers, and is 54 since Routeway - see
[section 13](13-routeway.md#13-routeway--probed-live-2026-09-29-and-what-the-limits-decided).**
The free-tier smoke guard reads both gateways' catalogues.

**KNOWN_DEAD, at the user's call: dead routes are MOVED TO THE TAIL, never
deleted**, because a free model can come back. Today: GLM-5.2 on Kilo and on
OpenRouter (404 "unavailable for free"), DeepSeek V4 Flash on Kilo and on
OpenRouter. Two tests: no dead tier sits above the tail, and **every dead model
has a LIVE route above it** - GLM-5.2 and DeepSeek both live on LiteRouter.

**Groq is ALIVE.** Section 9's 403 was the VPN exit, not the provider -
re-checked, both tiers answer.

**The GitHub secrets `LITEROUTER_API_KEY` and `ORCAROUTER_API_KEY` exist** (both
created 2026-09-28; this used to say they were owed).

#### 12.3 THE BUDGET WAS WRONG, and the user found it

`PLANNER_BUDGET` shipped at **8,000** - "half of Gemma's 16,000, the other half
for the instructions and the question". **The rest of the call is nowhere near
half:**

```
16,000 / 1.1  (the _check_fits margin)                 ~14,500
- instructions ~2,000 · question ~500 · schema ~300     ~12,000
```

And Gemma's cap counts **INPUT only** (measured 2026-08-16, see
[two kinds of limit](../llm/quotas-and-pools.md#two-kinds-of-limit-and-they-are-not-the-same-thing)), so the planner's
answer needs no room there. **Now 12,000.** Still a CEILING: slice 4 computes
it per call (CC8), and M5 may still find smaller is better.

> **A reserve that is never itemised grows to fill the gap.** "Half for the
> rest" sounded prudent and wasted ~4,000 tokens of the only view the planner
> has. The report path already does this right - `reserve()` measures what the
> instructions really cost and gives evidence the remainder.

#### 12.4 Where file text enters the queries — settled, because it confused us

```
the PLANNER call     instructions + question + map. NO file text (D2)
extract_claims       reads the paper whole - but ONLY if the planner picks it
B's text             never read whole (it does not fit). It is SEARCHED, and the
                     retrieved chunks refine the next queries in the D4 loop
```

That is the Claude Code shape: the FIRST search comes from the question and a
view of the folders, and file text shapes later searches through the loop.
**Aider is NOT an example of this - it has no search at all**; the user opens
files by hand. The open choice is M9: put a small A's full text into the
planner call and merge it with `extract_claims`.

> **Name which of two things a word means before arguing from it.** "Files" in
> aider means files OPEN IN THE CHAT, not files uploaded. Reading it as ours
> produced a whole exchange of confusion.

#### 12.5 Still open

- **Nothing calls the map.** The planner is slice 4.
- `PLANNER_BUDGET` - M5, including the dynamic variant.

#### 12.6 Three small debts closed — 2026-09-28

Done on `main` at the user's instruction, with no branch.

```
the dead line      removed: replace(chunk, artifact_id=...) in ingest_source.
                   Nothing reads Chunk.artifact_id; _store takes the id itself
warm_embeddings    now calls the product's embed_batches for batching, pacing
                   and 429/503 waits. Its private copy is gone, so the script
                   now exercises the code that ships. Two things stay in the
                   script: Cohere's measured 100,000 tokens/minute (the
                   registry gives Cohere no Pace), and a resume after a READ
                   TIMEOUT, which has no status so embed_batches raises it
upload limit       MAX_UPLOAD_BYTES 5MB -> 10MB, the same as MAX_ARCHIVE_BYTES
```

**The upload limit was the real defect.** A `.zip` is ONE upload, so it meets
the per-file check first. At 5MB a 7MB zip was refused there and the archive's
10MB limit could never fire. The old test compared the archive limit with the
**whole-body** limit - the wrong ceiling, so it passed while the bug was live.
`test_an_archive_we_accept_must_be_able_to_reach_us` now compares it with
`MAX_UPLOAD_BYTES`. Mutation-verified: putting the upload limit back to 5MB
fires it.

Side effect: the whole-body limit is `2 x upload + 65,536`, so it is now
~20MB, and the two literal payloads that test it grew from 11MB to 21MB.
`MAX_FILE_BYTES` (one file inside a repository) stays 5MB.

**Still owed:** Cohere's 100,000 tokens/minute could move into the registry
as a `Pace`, so the product paces Cohere too. Not done - it changes product
behaviour and its embedding-time estimate.

#### 12.7 Jev has a FREE second route, through Netlify — 2026-09-29, LIVE

**Why it was needed.** The OpenRouter Jev tier is billed, and the account has
never been paid:

```
OpenRouter  total_credits $0.00   total_usage $0.0417   is_free_tier true
```

OpenRouter still answers our Jev calls on that unpaid balance. That is its
choice, not a plan, and it can stop at any time.

**What was built.** Netlify's AI Gateway injects its OWN TypeSafe key, but only
into code running on Netlify. So a tiny function there is the bridge:

```
LabPilot --Bearer JEV_PROXY_SECRET--> labpilot-jev-0e3591.netlify.app/api/jev
         --Netlify's key--> TypeSafe POST /v1/systemone  (jev-1.13.0)
```

- **The proxy** is the separate folder `../labpilot-jev-proxy` (NOT in this
  repo): one function, `netlify.toml`, a README. No LabPilot logic, so a
  question change never needs a redeploy - a production deploy costs 15 of the
  Free plan's 300 monthly credits (180 credits = $1 of model spend).
- **The tier** is `JEV_NETLIFY_RERANK`, position 4 of the assembled rerank
  chain, directly behind `JEV_RERANK` - the twin rule `_both_accounts` applies
  to Google. `JevReranker` gained `url_env`: the address is read from
  `JEV_PROXY_URL` at call time, and an unset one is a RerankError BEFORE any
  request, so the chain skips it for free. TypeSafe's native shape is identical
  to OpenRouter's decisions endpoint, so nothing else changed.
- **Chain 3 is thirteen tiers now**, Cohere at 11.

**Proven live, exit AS24940 Hetzner Online, Nuremberg:** the diagnostic GET
answered `key_present: true` - **the AI Gateway works on the FREE plan**,
which the Jev investigation of 2026-09-19 could not confirm. Both Jev smoke
tiers passed. A POST with no secret or a wrong one answers 403.

**Two traps met on the way:**

- A new Netlify site sits behind **team login protection** (`sso_login`) by
  default, so every request got a login redirect. It was turned off for this
  one site only, at the user's instruction; the shared secret is what protects
  the function now.
- The proxy was tested locally in Node against a FAKE upstream before any
  deploy, so the first real call was not also the first test.

Mutation-verified: moving the Netlify tier away from its twin fires the
placement test; making an unset URL fall through to a request fires the
"costs no request" test alone. GitHub secrets `JEV_PROXY_URL` and
`JEV_PROXY_SECRET` were added by the user.
