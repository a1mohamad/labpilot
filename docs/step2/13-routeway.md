# Section 13: Routeway

[Docs home](../README.md)

### 13. ROUTEWAY — probed live 2026-09-29, and what the limits decided

*Raised by the user: section 10.5 recorded Routeway's DeepSeek as working and
nothing ever wired it in, so it was a gap and not a rejection. Probed first with
`scripts/models/probe_routeway.py`, then added on `feat/routeway` (merged: `main`,
`origin/main` and `feat/routeway` were the same commit, checked 2026-09-29).
Exit `91.107.152.24`, AS24940 Hetzner Online, Nuremberg, Google 200. Suite
**839 passed, 5 skipped**, ruff clean; 6 registry mutations and 2 smoke
mutations, every one fires alone. **CHAIN was 54 tiers** (56 since the
Gemma 26B tiers of 2026-09-30).*

#### 13.1 THE LIMITS ARE THE DECISION — every number from the API

```
quota     5 requests a MINUTE and 200 a DAY, ONE budget across all models
          (the day counter fell across different models, 200 -> 172 in 28 calls)
window    a HARD cap per free route, counted over prompt PLUS requested output,
          named in the 400 "Max context tokens: N":
              deepseek-v4-flash:free     42,000   (the model itself holds 1M)
              minimax-m2.7:free          42,000
              the six Gemma variants     62,000
              muse-glimmer-30b:free     131,072
          41,901 tokens passed, 45,954 was a 400.
          max_tokens 131072 on a TEN-token prompt is a 400 as well.
```

That matches how `_check_fits` already works (the SUM against one window), so
no new mechanism was needed - only a list. A report needs 26,000 of prompt and
32,000 of output; **DeepSeek's 42,000 cannot hold it**, so
`CONTEXT_TOO_SMALL` in `tests/unit/llm/test_registry.py` names it, and a test
proves it is refused locally for free. The Gemma variants' 62,000 holds a
report (60,600 padded), so they are eligible for one.

The catalogue is the provider's own data and carries `context_length`,
`capabilities`, `supported_parameters` and `pricing`; the website answers
WebFetch with 403. **`reasoning_effort` is NOT in these models' supported
parameters** (only Muse Glimmer lists it), so no `extra_body` is sent.

#### 13.2 WHAT WAS MEASURED, model by model

| model | result | verdict |
|---|---|---|
| **6 Gemma 4 26B A4B variants** | 18 of 18 "ok" pings; the real code question 5 of 6 (the sixth a proxy timeout); 1-4s; a tool call in 2.2s | **added** |
| **DeepSeek V4 Flash** | 3 of 3 whole answers to the real question, 2-11s, a correct diagnosis; a tool call in 2.4s | **added, and the flakiest of the set** |
| MiniMax M2.7 | 0 of 3 whole: `<think>` arrives INSIDE the reply text, 550-1,024 tokens per sentence, 8-58s | **left out** |
| Muse Glimmer 30B | 0 of 3 whole: a 57s cut at 1,024 tokens, two 60s timeouts, one 502 | **left out** — Requesty's route answers in 2.3s |

**Only the six Gemma variants are community finetunes, and the catalogue says
so in its own words:** *"a community creative finetune"*. They are NOT the
stock model. Stock Gemma 4 26B A4B is **17** on AA v4.3.2 (reasoning), read
from Artificial Analysis's own page, and the variants have no score of their
own. They sit BELOW the measured Gemma 4 31B (15) **on purpose: no evidence,
no promotion.** The order among the six rests on ONE sample each and means
nothing. MiniMax M2.7 is **23** on the same index (#38 of 116 open-weights,
63.9 tok/s, 205k context), the same as Flash-Lite - which is why leaving it out
is a real loss and was not done lightly.

**DeepSeek on Routeway sits at position 10 and is the least reliable tier
added.** In one session it gave a 429 `model_overloaded` (their congestion, per
model), a 502 Cloudflare page, and hangs past 60s on the trivial prompts and on
a 29K one. LiteRouter's and OrcaRouter's DeepSeek routes answered 21 of 21.
It stays because a failure costs one fast call, its timeout is bounded, and it
adds an independent 200/day - but **if it keeps failing, move it to the tail
next to the Gemma variants rather than leaving it ahead of Qwen and Gemini
3.6.**

#### 13.3 THREE THINGS THE PROBE CAUGHT THAT A "200" HID

**HTTP 200 is not an answer.** The first ping said "reply with one word: ok"
and counted DeepSeek as answering because the text was non-empty. The text was
`ok.ok.ok. responseok. responseok.` at `finish=length` - a repetition loop.
Run again on a real question the same model answered correctly in 6-8s, at
temperature 0 **and** 0.6, so it is the prompt shape and not our setting. The
probe now counts a reply only when it is 200, **stopped on its own**, has text
and did not leak `<think>`.

> **A one-word prompt tests the prompt, not the model.** This is the same
> family as "a shape check is not a content check" from session 10.

**Routeway caches identical requests** (`x-cache-status: MISS`, `x-cache-ttl:
3600`), so a repeated probe prompt can report a latency and a success that
never touched a model. Every probe prompt carries a nonce.

**The ~10s failures were OUR PROXY, not Routeway.** Six calls failed at 10.2s
with `ReadTimeout`, and the live smoke run finally named it: `Read timed out.
(read timeout=10.0)` on a call configured `(10, 180)`. That is the CONNECT
timeout - the VPN's HTTP proxy took longer than 10s to open the tunnel
(`HTTP/1.1 200 Connection established` appears in the raw response). Read a
failure's DURATION before blaming the provider: 10.2s is a tunnel, 60s is a
hang.

#### 13.4 WHAT SHIPPED

```
llm/registry.py         ROUTEWAY_URL · _routeway() · ROUTEWAY_DEEPSEEK_V4_FLASH ·
                        six Gemma variants via _routeway_gemma()
                        ONE pool (ROUTEWAY_API_KEY) - 5/min and 200/day are
                        account-wide. max_output_tokens = context_window, because
                        there is no separate output cap
                        a per-tier `timeout`: (10, 120) DeepSeek, (10, 180) Gemma
scripts/models/probe_routeway.py   the instrument - ping, context, output, tools stages
tests/unit/llm/test_registry.py    CONTEXT_TOO_SMALL + a "costs no request" test,
                        the short-timeout test, GATEWAYS, the reasoning excuse
tests/smoke/test_gateway_tiers_are_free.py   Routeway's NESTED pricing
tests/smoke/test_every_tier.py   paced (13s) and retried for Routeway
.github/workflows/smoke.yaml     ROUTEWAY_API_KEY
```

**The timeout is per tier because Routeway HANGS instead of refusing.** The
default read timeout is 600s against a 900s chain budget, so one hang would
spend two thirds of it on a single dead tier. Real answers were 1-26s. The 180
in the test is a literal, so the test cannot follow the default upward.

**The smoke test was outrunning a published limit.** Seven Routeway tiers back
to back, six of them adjacent, came back **3 of 7** on the first live run:
`429 "Account per-minute rate limit exceeded (5 RPM)"`. With 13s between calls
and two retries for the transient cases (429, 502, no status at all) it is
**7 of 7**.

**⚠ ONE POOL MEANS ONE 429 RETIRES ALL SEVEN.** After its retries the chain
marks `ROUTEWAY_API_KEY` dead for the rest of the request. A DeepSeek
`model_overloaded` is per-model congestion, so it can skip six Gemma variants
that would have answered. Kept: those variants sit at the tail, the skip is
free, and the per-minute 429 - the common one - really does hit every tier.
Splitting the pool would make that case retry seven times.

#### 13.5 STILL OPEN

- **The GitHub secret `ROUTEWAY_API_KEY` exists** (created 2026-09-29, and
  `smoke.yaml` maps it). No weekly run has exercised the seven tiers yet.
- **MiniMax M2.7 is recoverable, at a price.** Stripping a leading
  `<think>...</think>` in `_visible_text` would make it usable, and it would
  need a large `max_tokens`. AA 23 is Flash-Lite's level, so it is worth
  revisiting if a strong slot is short.
- **The Chain 1 table in this file is STALE** - it lists 40 tiers and the chain
  has 54. Its positions have never been safe to quote; read `CHAIN`.
- **The Gemma variants are unscored.** Slice 1's latency ranking will rank them
  by speed; a quality score needs the same fixture the other tiers had.
- **The rerank chain was not touched.** Routeway's Gemma variants could be
  rerank tiers (stock Gemma 26B tied the 31B at MRR 0.732) - untested, and a
  finetune is not the stock model.
