# Section 16: Mistral chat models at zero

[Docs home](../README.md)

### 16. MISTRAL'S CHAT MODELS ARE AT ZERO, AND THE CALL WAS NOT THE PROBLEM — 2026-10-05

*Raised by the user: "something is wrong in our call - it doesn't make sense that
something was accessible and now it is refused". Checked three ways - the
network, our request, and the whole Mistral catalogue - and then Mistral's own
docs and console. Exit AS24940 Hetzner, Nuremberg; Google 200 first. Suite and
mutation results are at the end.*

#### 16.1 What was ruled out

| suspect | test | result |
|---|---|---|
| **the network** | 35 calls in a row to `api.mistral.ai`, one second apart | **all 35 got a reply, 0.6 to 1.9 s each** (some replies were refusals, which is the point). No timeout. One earlier call did hang 90 s and the next took 0.4 s: a hiccup, not a pattern |
| **our request shape** | a bare curl body (model, one message, `max_tokens`, `temperature`) with no extras | same refusal. `reasoning_effort: "none"` changes nothing either |
| **the key** | `GET /v1/models` | 200. Both embedders answer 200 at **60 requests a minute** on the same key |
| **a spent quota** | the Subscription page | **$0 of $10 used, resets on the first of each month.** The allowance IS back, and the models still refuse |

#### 16.2 What it is: the account may call 11 models and not the rest

One tiny call to every chat-capable id (25 in the catalogue, 10 more of ours or old
ones). The header `x-ratelimit-limit-req-minute` is Mistral's own answer, and it
agrees exactly with the Limits page for every model that works (RPS x 60):

```
ANSWER 200      codestral-2508/-latest 125/min   ministral-14b 30/min   ministral-8b 188/min
                ministral-3b 750/min   open-mistral-nemo 188/min   mistral-code-latest
429, limit 0    mistral-medium-latest   mistral-small-latest   magistral-small/medium
                devstral-2512, devstral-latest, -medium-latest, -small-latest
                mistral-vibe-cli-*   and the old ids mistral-medium-2508/-2505 and
                mistral-small-2506/-2501
400 invalid     every DATED magistral-* and devstral-* id except devstral-2512
403 not in tier mistral-large-*   zai-glm-5-3   zai-glm-5-2   glm-5-2
403 labs        labs-leanstral-*
```

**Every model the catalogue marks `reasoning: true` is refused and every one marked
`false` answers.** That is a correlation over about 25 ids, not a cause: turning
reasoning off did not help.

#### 16.3 Why the names stopped meaning what they meant

The catalogue's own `aliases` field says Mistral MERGED models:

```
mistral-medium-latest  = Mistral Medium 3.5   aliases: mistral-medium, -3, -3-5, -2604,
                         magistral-medium-latest, mistral-vibe-cli-latest, -with-tools
mistral-small-latest   = Mistral Small 4      aliases: magistral-small-latest, mistral-vibe-cli-fast
```

So our THREE tiers ("Mistral Medium", "Magistral Small", "Devstral 2") are really
TWO models, and the old pinned versions no longer exist as themselves. Every dated
`magistral-*` and `devstral-*` id except `devstral-2512` answers 400 "invalid
model". `mistral-medium-2508` and `mistral-small-2506` answer the same limit-0 429,
which FITS a redirect to the new models but does not show one (a 429 does not say
which model served it). Redirects ARE shown for the small families, where a 200
names the model: `pixtral-12b-2409` is served by `ministral-14b`, `codestral-2501`
by `codestral-latest`, `mistral-tiny` by `ministral-8b`.

Mistral's changelog and models page (primary sources): Small 4 released
2026-03-16, Medium 3.5 on 2026-04-28, Magistral and Devstral "now deprecated" in
favour of them, and **"Devstral 2.0 moves to paid API access" (2026-01-27)**.
GLM 5.3 (`zai-glm-5-3`) became generally available 2026-09-28 and GLM 5.2 retires
2026-10-31. **When the alias moved, or when the free plan stopped covering the new
models, is not dated anywhere and was not found.**

#### 16.4 Mistral's console and its API DISAGREE

The Limits page lists `mistral-medium-latest` and `mistral-small-2603` at 20,000
tokens a minute and **1.00 requests a second**, and `mistral-large-2512` at
250,000 and 1.00. The API answers 429 with a limit of **0** for the first two and
403 `tier_not_allowed` for the third. The Subscription page says "you can create
API keys and use the free tier within the limits described on the limits page".

> **A console page is not an entitlement. Read `x-ratelimit-limit-req-minute`.**
> The same lesson as `GET /v1beta/models` returning 200 while every generation
> was refused, and as the Limits page listing `glm-5-2` in September.

Only Mistral can say which is right. A request id for them, from a refused
`mistral-medium-latest` call at 2026-10-05 10:09:51 GMT:
`01a10b8a-8a6c-7754-b703-02ae7ed7b7ba`. Enabling pay-as-you-go would test whether
it unlocks them, and needs a card, which this project does not use.

#### 16.5 What was changed

- `llm/registry.py`: **Mistral Medium, Magistral Small and Devstral 2 moved to the
  END of `CHAIN` and into `KNOWN_DEAD`**, kept so they can come back. The reasoning
  is written beside the list. CHAIN is still 56 tiers.
- `tests/unit/llm/test_registry.py`: `NO_LIVE_ROUTE` names the two with no other
  route (Magistral Small, Devstral 2), and a second test fails if a name there
  gains a live twin. `OUTPUT_TOO_SMALL` follows the new chain order.
- **Mutation-tested, all four fire alone:** dropping a name from `NO_LIVE_ROUTE`,
  excusing a tier that HAS a twin, taking a tier out of `KNOWN_DEAD` while it sits
  at the tail, and removing it from the tail while it is still listed dead.

#### 16.6 What it opens, and what is NOT known

- **Live and free on this key, never used here:** `ministral-14b` (262k context,
  30 requests a minute, 937,500 tokens a minute, no reasoning, tools yes),
  `codestral` (256k, 125 a minute), `ministral-8b`, `ministral-3b`,
  `open-mistral-nemo`. **None has an Artificial Analysis score looked up**, so
  none is placed in the chain: no evidence, no promotion.
- **Not known:** why the plan covers the small families and not Medium 3.5 and
  Small 4; whether Mistral will change it; whether a new API key or a card changes
  anything (a new key is a cheap test, and the user would put it in `.env`).
- **The retry of the failed latency tiers** is in `docs/step2/slice1/RESULTS.md`
  section 12. In short: Qwen3.8 27B on Kilo works now, the Gemini 3.6-3.8 tiers
  answer about half the time, Laguna on Kilo cannot write a long answer, and the
  Mistral chat tiers and Inkling Small are refused on every call.
