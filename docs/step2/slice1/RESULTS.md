# Step 2, slice 1 - how fast is every tier?

**Measured 2026-09-29. 50 tiers, 300 requests, plus 41 re-measured.** The raw
data is `artifacts/step2/latency/2026-09-29_18-29.jsonl` (git-ignored, like every
run file). The instrument is `scripts/measure_latency.py`; its tests are
`tests/unit/test_measure_latency.py`.

Read the [caveats](#what-this-does-not-tell-you) before quoting a number. The
short version: **this is one afternoon, one exit, three samples per cell, and an
answer of about 500 tokens.** It ranks the tiers. It does not yet say how long a
5,000-token report takes.

---

## 1. What was measured

Two fixed jobs, three rounds each, one request at a time, no retries:

| probe | the job | tokens written |
|---|---|---|
| **short** | a correspondence-gate verdict, one JSON object | about 30 (a thinking tier writes 200-550) |
| **long** | explain why two benchmark numbers differ, about 300 words | about 400 to 2,500, and once 5,644 (DeepSeek on OrcaRouter, 5,243 of it reasoning) |

Per tier, the script keeps the **median** seconds of the successful calls and
their **range**, how many calls **answered**, and the tokens the provider says
the model wrote (reasoning included).

- **A failure is a result.** A 503, a 429 and an empty answer are counted, not
  retried. A tier that answers fast and fails half the time is reported as both.
- **The network is not a result.** A call that never reached the provider (the
  VPN tunnel did not open in 10 seconds) says nothing about the model. It is kind
  `network`, it is retried, and it never counts in a tier's numbers.

**What the network did to the run.** It collapsed for parts of it. 41 of 300
samples were lost, 20 of them in the last 25 calls. A `--fill` mode re-ran exactly
those 41 (`--fill FILE`), and now every one of the 300 slots holds a real answer.
**The 41 were measured about two hours after the rest** (20:38 UTC against
18:29 UTC), from a different address on the same ISP. Nothing was rewritten: the
new samples supersede the failures in the same file.

The successful samples inside the two bad stretches were compared with each
tier's own other samples, and only 2 of 19 were more than twice as slow. So the
damage was missing samples, not distorted ones.

## 2. The ranking

Ordered by the **measured** median of the long job, fastest first. `ok` is
answered / calls. `long range` is the fastest and slowest successful call.
`tok/s` is tokens written per second at the long job, fixed cost included.
`s/1k fit` is the slope between the two probes and is drawn **only** when they
differ by 200+ tokens.

```
 #  tier                                  ok  short s  long s  long range  tok/s  s/1k fit  notes
------------------------------------------------------------------------------------------------------------------------
 1  GPT-OSS 120B (Groq)                 6/6       2.2     4.1         4-5    330       1.8  
 2  DeepSeek V4 Flash (LiteRouter)      6/6       3.9     6.3         5-8     60       7.0  
 3  Gemini 3.5 Flash-Lite (key 2)       6/6       3.3     7.4         7-8    183       4.3  
 4  Gemini 3.5 Flash-Lite               6/6       2.9     8.0         8-9    189       4.5  
 5  Gemini 3.1 Flash-Lite (key 2)       6/6       7.5     8.1         6-9    155       0.6  
 6  GLM-5.3 Flash (Cline)               6/6       3.2     8.3         8-9     59      11.6  
 7  Qwen3.8 27B (Groq)                  5/6       1.3     8.3         7-9    344       2.6  error x1
 8  Gemini 3.1 Flash-Lite               6/6       7.6     8.4        6-12    146       0.8  
 9  Laguna S 2.1 (Cline)                4/6       3.1     8.8         9-9     38      18.7  http-500 x2
10  Mistral Medium (LiteRouter)         6/6      10.3     9.3        9-12     52         -  
11  Gemini 3.5 Flash                    6/6       3.8     9.3        9-11    169       5.1  
12  North Mini Code                     6/6       6.4     9.4        3-13     47         -  
13  North Mini Code (Kilo)              6/6       7.6     9.8        4-19     43         -  
14  Nemotron 3 Super                    5/6       3.6    10.2        8-13     63      13.2  error x1
15  Gemini 3.5 Flash (key 2)            6/6       4.1    10.7       10-13    161       5.6  
16  DeepSeek V4 Flash (OrcaRouter)      6/6       3.6    12.5       10-35    120       6.4  
17  DeepSeek V4 Flash (Routeway)        6/6       2.4    14.4       12-63     32      31.5  
18  Nemotron 3 Super (Kilo)             5/6       2.9    15.7        8-24     45      23.5  error x1
19  Gemini 3.8 Flash (key 2)            1/6         -    15.9       16-16    142         -  http-503 x5
20  Gemini 3.6 Flash (key 2)            3/6       4.1    15.9       16-16    128       6.8  http-503 x3
21  Gemma 4 26B A4B Chimerax (Routeway)  6/6       2.8    16.6       14-19     23      40.7  
22  Gemma 4 26B A4B Moonlight (Routeway)  6/6       3.5    16.7       15-19     22      40.3  
23  Gemma 4 26B A4B Darksoul (Routeway)  6/6       4.2    17.6       17-37     21      40.1  
24  Step 3.7 Flash (Kilo)               3/6       9.2    17.8       16-20    185       4.9  error x3
25  Qwen3.8 27B (LiteRouter)            5/6       4.6    18.1       14-27    111       7.1  http-403 x1
26  Gemma 4 26B A4B Musica (Routeway)   6/6       3.4    18.6       15-37     20      45.7  
27  Gemma 4 26B A4B MeroMero (Routeway)  6/6       4.1    18.6       15-20     20      43.2  
28  Gemma 4 26B A4B Luminous (Routeway)  6/6       4.0    19.1       17-27     19      46.3  
29  Qwen3.8 27B (Kilo)                  1/6         -    29.4       29-29     34         -  http-429 x5
30  GPT-OSS 120B                        6/6       5.2    30.2       22-31     59      16.2  
31  GLM-5.3 Flash (LiteRouter)          6/6       5.5    30.7       22-31     19      46.9  
32  GLM-5.2 (LiteRouter)                6/6       7.0    32.1       24-44     47      19.9  
33  Nemotron 3 Ultra (Requesty)         5/6       9.9    33.8       33-35     16      81.0  http-429 x1
34  Nemotron 3 Ultra                    5/6      16.6    35.0       28-43     17      52.9  error x1
35  Gemma 4 31B (Requesty)              6/6       8.8    38.2       32-38     34      27.8  
36  Nemotron 3 Ultra (Kilo)             4/6      16.4    46.5       26-67     12     102.5  error x2
37  Muse Glimmer 30B (Requesty)         6/6      27.6    50.5       46-81     28      21.5  
38  GLM-5.3 Flash (OrcaRouter)          6/6       7.6    66.2      66-107     45      21.8  
39  Qwen3.8 27B                         4/6       4.5    83.7       84-84     30      33.3  error x2
40  Gemma 4 31B                         3/6      32.5    85.4       76-95     17      44.2  http-500 x3
41  Gemma 4 31B (key 2)                 4/6      55.5    91.3      61-121     13      38.5  http-500 x2
42  Laguna S 2.1 (Kilo)                 3/6       3.3       -           -      -         -  error x2, http-502 x1
43  Gemini 3.6 Flash                    2/6       5.0       -           -      -         -  http-503 x4
44  Gemini 3.8 Flash                    2/6       8.3       -           -      -         -  http-503 x4
45  Gemini 3.7 Flash                    0/6         -       -           -      -         -  http-503 x6
46  Gemini 3.7 Flash (key 2)            0/6         -       -           -      -         -  http-503 x6
47  Inkling Small (Kilo)                0/6         -       -           -      -         -  http-429 x6
48  Mistral Medium                      0/6         -       -           -      -         -  http-429 x6
49  Magistral Small                     0/6         -       -           -      -         -  http-429 x6
50  Devstral 2                          0/6         -       -           -      -         -  http-429 x6

seconds are medians of SUCCESSFUL calls and long range is their min-max: one tier varied 4-19s between rounds. tok/s is tokens written per second at the long probe, fixed cost included. s/1k fit is drawn only when the two probes differ by 200+ tokens.
```

| how fast at ~500 tokens | tiers |
|---|---|
| **10 seconds or less** | 13 |
| **10 to 30 seconds** | 16 |
| **over 30 seconds** | 12 |
| **no long answer at all** | 9 (six of them never answered either probe) |

## 3. What it shows

### 3.1 The route matters more than the model

The same model on different hosts, median long-answer seconds:

| model | fastest route | slowest route |
|---|---|---|
| GPT-OSS 120B | **Groq 4.1** | Cloudflare 30.2 (7x) |
| GLM-5.3 Flash | **Cline 8.3** | LiteRouter 30.7 - OrcaRouter 66.2 (8x) |
| Qwen3.8 27B | **Groq 8.3** | LiteRouter 18.1 - Kilo 29.4 - Cloudflare 83.7 (10x) |
| DeepSeek V4 Flash | **LiteRouter 6.3** | OrcaRouter 12.5 - Routeway 14.4 |
| Gemma 4 31B | **Requesty 38.2** | Google 85.4 - Google key 2 91.3 |
| Nemotron 3 Ultra | **Requesty 33.8** | OpenRouter 35.0 - Kilo 46.5 |

**`CHAIN` orders the routes of one model by quota (the bigger free allowance
first), never by speed.** For Qwen that puts Kilo (29 s, and 1 answer in 6) and
Cloudflare (84 s) ahead of Groq (8 s). Groq is last for a real reason - its
8,000 tokens a minute cannot take a big prompt - but that is a reason for the
big jobs, not for the small ones.

### 3.2 The newest Gemini models are the least available

| tier | answered | what it said |
|---|---|---|
| Gemini 3.7 Flash, both keys | **0 of 12** | 503 every time |
| Gemini 3.8 Flash, both keys | **3 of 12** | 503 |
| Gemini 3.6 Flash, both keys | 5 of 12 | 503 |
| Gemini 3.5 Flash and both Flash-Lites (6 tiers) | **36 of 36** | - |

Google's own message is "This model is currently experiencing high demand".
**Positions 4-7 of `CHAIN` are 3.8 and 3.7 Flash, and they answered 3 of 24
times.** Whenever the chain reaches them it spends a request and a retry on a
tier that almost never answers.

### 3.3 Thinking is most of the "fixed cost"

Asked for a 30-token verdict, Gemini 3.5 Flash wrote **566 tokens, 529 of them
reasoning**, and took 3.8 s. Laguna (Cline) wrote 30 tokens with no reasoning and
took 2.8 s; DeepSeek on LiteRouter wrote 32 tokens and has a median short time of
3.9 s. **For a short node the
model's speed matters less than how much it thinks.** On Gemini that is a setting
we control (`thinking`), and CLAUDE.md already measured it once: the same answer,
3x the time, 930 thought tokens.

### 3.4 One tier varied fivefold between rounds

North Mini Code (Kilo) took **18.6, 9.8 and 4.3 seconds** for the same job with
about the same number of tokens (422, 401, 481). DeepSeek on Routeway ran 12 to 63. **Three samples per
cell give a median, not a promise**, which is why the range is printed beside it.

### 3.5 Tier 1 is not slow at this size

GLM-5.3 Flash on Cline wrote about 500 tokens in 8.3 s, 59 tokens a second. At
that rate a 5,000-token report would take about 85 seconds, and the measured
reports took **119 to 497**. So the 400-second problem is not explained by this
table: either the reports are far longer than 5,000 tokens of writing, or the
sustained speed falls a long way below what a 500-token answer shows. Speed also
differs a lot by tier: one sample already reached 5,644 tokens (DeepSeek on
OrcaRouter, mostly reasoning) in 35 seconds, about 160 tokens a second. **That is
the question the next measurement has to answer** (section 5).

### 3.6 Reliability is a second axis

Speed alone hides the tiers that often fail. Answered fewer than 3 of 6:

| tier | why |
|---|---|
| Mistral Medium, Magistral Small, Devstral 2 (the three Mistral-hosted tiers) and Inkling Small (Kilo) | 429 on every call, 0 of 6 - a spent quota |
| Gemini 3.7 Flash x2 | 503 on every call, 0 of 6 |
| Qwen3.8 27B (Kilo) | 429 on 5 of 6 - its upstream pool was full |
| Gemini 3.8 Flash (key 2) | 503 on 5 of 6 |

Gemma 4 31B on Google is slow (76 to 121 seconds) **and** answered only 3 of 6
(key 1) and 4 of 6 (key 2), with HTTP 500 on the rest.

### 3.7 Two failures were not the provider being down

**Nemotron 3 Ultra and Nemotron 3 Super, on OpenRouter and on Kilo, answered
HTTP 200 with an error inside the body** (5 samples in all; every one shows an
`error` object where `choices` should be). The full message was read only for
Kilo's, raw, on 2026-09-30:

```
{"message": "Upstream error from Nvidia: Service temporarily overloaded",
 "code": 503, "metadata": {"error_type": "provider_overloaded"}}
```

Our reader has no `choices` to read, so it reports "unexpected response shape"
with the body cut off. Two things are lost: **the reason**, and **the
classification** - it is a 503, which the six-way rule retries on the same tier,
but the chain sees a failure with no status and moves on. **Not fixed; it is a
product change.** It reproduced 2 times in 6 calls on Kilo and 0 in 6 on
OpenRouter's own Nemotron 3 Ultra.

**Step 3.7 Flash on Kilo returned "an empty answer" 3 times in 6, and the raw
reply shows why:** `finish_reason: length`, `content: ""`, and 8,000-9,000
characters of reasoning. It spent the whole 2,048-token budget thinking about a
30-token answer. That is the reasoning-burn failure this project has met before,
and it is a property of the tier at a small budget, not a flaky endpoint. **Qwen3.8
27B on Cloudflare and Groq and Laguna on Kilo also returned empty answers; their
raw replies were not captured**, so "the same cause" is likely, not shown.

## 4. What this suggests for Step 2

These are candidates for the routing slice, not decisions. Each rests on the
caveats below.

- **Short nodes (gate, planner, verify):** low thinking on a fast tier. On
  measured short time and answer rate: Qwen3.8 27B on Groq (1.3 s, 5 of 6), GPT-OSS
  120B on Groq (2.2 s, 6 of 6), Gemini 3.5 Flash-Lite (2.9-3.3 s, 12 of 12),
  Laguna on Cline (3.1 s, 4 of 6). Groq's 8,000 tokens a minute suits a small job
  and rules it out for a big one.
- **Medium prose (about 500 tokens):** DeepSeek V4 Flash on LiteRouter (6.3 s), the
  two Flash-Lites (7-8 s), GLM-5.3 Flash on Cline (8.3 s).
- **Order the routes of one model by speed** (section 3.1).
- **Do not put a tier that answers under half the time in a latency-sensitive
  node**, however good its model is (section 3.2, 3.6). The chain pays for every
  miss in seconds.
- **Do not send a small token budget to a heavy thinker** (Step 3.7 Flash).

## 5. What this does not tell you

- **Report length is not measured.** The long job is about 500 tokens. A report is
  10 times that, and speed does not scale in a straight line. A probe of about
  3,000 tokens on the top 10 to 15 tiers is the next measurement, and the answer
  to the 400-second problem depends on it.
- **Three samples per cell, one afternoon, one country.** The exit was AS24940
  Hetzner, Nuremberg, and its address changed during the run. Failures cluster in
  time - a bad window shows in every tier it touches - so a second run at another
  hour could reorder neighbours. **Gaps under about 30 percent are noise.**
- **The 41 re-measured samples come from a different window** (about 2 hours
  later). If the load changed, they carry it.
- **The original 300 samples have no timestamps.** Only the run start and the
  fill samples do. Every new sample has one.
- **The token budget shaped some failures.** The short probe allows 2,048 tokens.
  A node that gives a thinking tier more room would not fail the way Step 3.7 Flash
  did.
- **Only the generators were measured, not the rerankers.** Their speed is known
  only from slice 6 (Flash-Lite about 1.3 s, Jev 1.2-1.6 s, Gemma 26B about 19 s,
  Gemma 31B about 23 s).
- **Known dead routes were not called** (GLM-5.2 on Kilo and OpenRouter, DeepSeek
  V4 Flash on Kilo and OpenRouter).
- **The Mistral tiers say nothing about Mistral's speed.** All three answered 429
  on every call, and the account's monthly quota is reported spent.

## 6. Reproduce it

```bash
PYTHONPATH=. python scripts/measure_latency.py --dry-run
PYTHONPATH=. python scripts/measure_latency.py
PYTHONPATH=. python scripts/measure_latency.py --fill artifacts/step2/latency/RUN.jsonl
PYTHONPATH=. python scripts/measure_latency.py --report artifacts/step2/latency/RUN.jsonl
```

**Check the exit ISP first** (CLAUDE.md's network precondition). The dry run prints
the requests each quota pool will be asked for; the Gemini Flash tiers allow only
20 a day each, so a full three-round run uses 6 of them per pool.
