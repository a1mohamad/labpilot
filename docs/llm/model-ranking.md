# Model ranking

[Docs home](../README.md)

### Model ranking — how the order was decided (2026-08-11)

**Vendor benchmarks were wrong twice.** NVIDIA's blog claims Nemotron 3 Ultra
scores 86.7% GPQA Diamond and 71.9% SWE-bench; Mistral calls Large 3
"state-of-the-art, frontier-class". Two independent sources contradict both.

| Model | AA Intelligence Index | LMArena Elo / rank |
|---|---|---|
| GLM-5.2 | **53** | 1470 / #33 |
| Gemini 3.6 Flash | **52** | **1484 / #15** |
| Gemini 3.5 Flash | 47 | 1477 / #19 |
| Nemotron 3 Ultra | 38 | 1426 / **#96** |
| North Mini Code | 27.6 (**coding 33.4**) | not listed |
| Devstral 2 | 19 (SWE-bench 72.2%) | not listed |
| Mistral Large 3 | 16 | 1415 / **#118** |

The two sources measure different things and LabPilot needs both:
- **Artificial Analysis** — 9 benchmarks, pass@1, weighted **agents 34% · coding
  24% · scientific reasoning 24% · general 18%**. That weighting is unusually well
  matched to LabPilot: 82% of the index is agents + code + science reasoning.
- **LMArena** — blind human A/B votes. Measures **explanation quality**, which is
  what LabPilot actually shows the user.

$$
I = \sum_{i=1}^{9} w_i \, s_i , \qquad \sum_i w_i = 1
$$

Reading rule: AA's confidence interval is **±1%**, so 53 vs 52 is a *tie* and
52 vs 38 is a *real gap*. Gemini 3.6 Flash takes tier 1 over GLM-5.2 on the
LMArena tiebreak (#15 vs #33) plus multimodality and verified availability.

**Corrections this produced:**
- **Nemotron 3 Ultra is not the primary.** It is mid-pack — LMArena #96. It moves
  from tier 1 to tier 4. Its **1M context is real** (NVIDIA's model card:
  "Context Length: Up to 1 million tokens"); Artificial Analysis's 262K figure is
  a deployment default, not the model's limit.
- **Mistral Large 3 is excluded entirely** — AA 16 (below its class median of 18),
  LMArena #118, 41 tok/s, released December 2025.
- **Codestral is excluded** — 52% SWE-bench vs Devstral's 72.2%, and it is a
  **fill-in-the-middle autocomplete** model, not a conversational one. It would be
  the right choice only if LabPilot ever adds in-editor gap completion.
- **Groq is excluded on TPM, not quality** — see Constraints.
  *(Partly reversed 2026-08-17: it is now tier 12, reachable for small jobs only.)*

#### Re-measured 2026-08-17 — the scores the 15-tier order is built on

Two sources again, both re-read rather than remembered. Scores move fast: Google
shipped **three** new Flash models in three months.

| Model | AA Index | LMArena | Where |
|---|---|---|---|
| Gemini 3.7 Flash | **56.0** | — | Google |
| GLM-5.2 | 52.6 | 1465 (#13) | Mistral ❌ |
| Gemini 3.6 Flash | 51.6 | 1484 (#15) | Google |
| Gemini 3.5 Flash | 50.2 | **1480 (#4)** | Google |
| Nemotron 3 Ultra | 38.3 | 1426 | OpenRouter |
| **Gemini 3.5 Flash-Lite** | **37.4** | — | Google |
| Mistral Medium 3.5 | 30.4 | 1420 (#50) | Mistral |
| Gemma 4 31B | 29.7 | **1441 (#27)** | Google |
| North Mini Code | 27.6 | — | OpenRouter |
| Nemotron 3 Super | 25.7 | 1378 (#83) | OpenRouter |
| GPT-OSS 120B | 24.1 | 1365 (#98) | Cloudflare · Groq |
| Nemotron 3.5 Lightning | 23.6 | — | OpenRouter |
| Mistral Small 4 | 19.7 | — | Mistral |
| Devstral 2 | 19 | — | Mistral |

**Not listed anywhere:** Magistral Small, Gemini 3.1 Flash-Lite. Their tier
positions are guesses and are labelled as such in the chain table.

**Two corrections this round produced, and both were errors of *reading*, not of
judgement:**

- **North Mini Code is AA 27.6.** That number was already in this file, and I
  recorded it as "no score" while ranking it. It moved 12 → 9. **Search your own
  notes before declaring something unmeasured.**
- **Gemini 3.5 Flash-Lite at 37.4 beats every non-Gemini model below tier 6** —
  Mistral Medium, Gemma, GPT-OSS, Nemotron Super — while having **25× their
  daily budget** and spending **zero thinking tokens**. It is the single best
  value in the project and was found only because the user asked whether
  Flash-Lite models were usable at all.
