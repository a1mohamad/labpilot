# Google keys and gemini-embedding-2

[Docs home](../README.md)

### `gemini-embedding-2` — newer, and the only entry ranked on someone else's benchmark

*Read from Google's own model listing and docs on 2026-09-11. **No call was
made to the model** — the user asked for the question to be answered by
research, not by spending quota, and the provider's own metadata answers it.*

| | `gemini-embedding-001` | **`gemini-embedding-2`** |
|---|---|---|
| `version` field | `001` | **`2`** |
| input limit | 2,048 | **8,192** |
| MTEB, mean by task | 68.32 | **69.9** |
| dimensions | 3072 | 3072 |
| modality | text | **multimodal** |

So it is newer on every axis the provider publishes, and `MIGRATION` now runs
**codestral → BGE → mistral-embed → embedding-2 ×2 keys → embedding-001 ×2
keys → Cohere**: eight entries, four of them Google, four independent
1,000/day buckets.

> **This is the ONLY entry in `MIGRATION` ordered on somebody else's
> benchmark**, and that breaks this file's own rule that the order comes from
> recall measured on OUR fixture. `embedding-001` is the model holding that
> measurement — recall@5 of **1.000**, the only model to manage it.
> **Slice 8 owes `embedding-2` a score**, and if it loses there the order moves
> back. `test_the_newer_google_embedder_outranks_the_older_one` exists to keep
> that deliberate rather than forgotten.

**The two spaces are INCOMPATIBLE** — Google states it explicitly. That is not
a footnote, it is why `MIGRATION` is a *migration*: moving a corpus from 001 to
2 means **re-embedding all of it**, and the only free continuation is the same
model on the other key.

**It lifts a ceiling this file called permanent.** 001's 2,048-token limit meant
*"chunks must stay small"* and *"it removes the option of ever raising that
cap"*. 8,192 does not bind at any chunk size we would choose, so the 510-token
cap is now a decision rather than a constraint.

**One rename, because the old names became a trap.** `GEMINI_EMBEDDING_2` used
to mean *"001 on the second key"* — precisely the wrong thing to guess once a
model literally called `gemini-embedding-2` exists. The four entries are now
`GEMINI_EMBED_001`, `GEMINI_EMBED_001_KEY2`, `GEMINI_EMBED_2`,
`GEMINI_EMBED_2_KEY2`.

**`score_hybrid.py`'s `google` stays on 001 deliberately.** Its cache is keyed
by model, so repointing that name would silently re-embed and make every
recorded Google number incomparable with the old runs. `embedding-2` is a
separate `google2` entry.

### Two Google accounts — added 2026-09-11, and it needed no new mechanism

**Google bills per PROJECT per MODEL.** The 429 body says so:
`GenerateRequestsPerDayPerProjectPerModel-FreeTier`. So a second account is not
a spare key — it is **a fresh daily allowance for every model at once**.

| | one account | two accounts |
|---|---|---|
| each Flash model | 20/day | **40/day** |
| each Flash-Lite | 500/day | **1,000/day** |
| each Gemma | 14,400/day | **28,800/day** |
| `gemini-embedding-001` | 1,000/day | **2,000/day** |

**`quota_pool` already made this a data change.** It exists precisely because
*"authentication and accounting are different questions"* — so the pool simply
had to carry the key as well as the model:

```
GOOGLE_API_KEY:gemini-3.5-flash        tier 5
GOOGLE_API_KEY_2:gemini-3.5-flash      tier 6
```

Each Google model now appears **twice, adjacent**, and the existing pool-aware
skipping does the rest: a spent account is marked dead and its twin is tried
for free. `CHAIN` went from 15 tiers to **21**.

> **Collapsing the key and the pool would mark BOTH accounts dead the first
> time either one was spent** — the exact mistake `quota_pool` was created to
> fix on 2026-08-16, arriving again one level up.

**Adjacency is correct here**, for the reason the 2026-08-16 rewrite
established: a spent pool costs nothing to skip, so the twin is the strongest
model still available. Ordering by capability then means *"the same model on
the other account"* beats *"a weaker model on this one"*.

**`tier` is now derived from POSITION.** Reordering `CHAIN` without renumbering
`tier=` was a real bug on 2026-08-11 — the chain read `2, 2, 3, 1, 4, 6` and
only an invariant test noticed. Deriving it makes that class of bug impossible
rather than merely tested for.

#### For the EMBEDDER it is the only fallback that does not force a re-embed

`MIGRATION` is a migration order, not a fallback chain: every other step means
re-embedding the whole corpus, because two models' vectors do not compare. **The
same model on a second account is the exception** — identical model, identical
vectors — so a corpus half-ingested on key 1 can be *finished* on key 2.

**Verified live rather than assumed: the two accounts return BIT-IDENTICAL
vectors, maximum element difference `0.00e+00`.** Without that check, "resume on
the other key" would have been a guess that silently poisons a corpus.

#### What was measured when it went in

**12 of 12 Google tiers answer on both keys.** Gemma needed a retry on *both*
accounts equally — it returns HTTP 500 about one call in three, which is
Google's serving of that model and not the key.

**Three invariants changed MEANING and were corrected rather than deleted:**

- models may now repeat, so what must stay unique is the **(model, key)** pair —
  and a repeat on *one* key is dead weight and still fails the build
- pools must be unique **per Google tier only**. OpenRouter genuinely has one
  account-wide 50/day, so its three tiers correctly share a pool; a global
  uniqueness rule would have been demanding the wrong thing, and measured, it
  failed on 5 tiers that were behaving properly
- the thinking and input-limit exception lists now match on **model**, because
  the display name carries a `(key 2)` suffix

**The standing caution has not changed.** This project already lost a Google
account to an anti-fraud flag on 2026-08-11, and several accounts driven from
one VPN exit is the pattern that triggers it. See
[the network precondition](../rules/sources-and-network.md#network-precondition--check-the-exit-isp-before-any-llm-work).
