# Development environment

[Docs home](../README.md)

## Development Environment

Windows 11. **Git Bash** is the preferred shell (PowerShell also works, but the
commands below assume Git Bash).

### Hardware limits — important
This machine has **4–6GB VRAM and 8GB or less system RAM**.

Consequences, decided 2026-08-08:
- **Running any model locally is ruled out.** A 4B model in 4-bit needs ~3GB for
  weights alone, and the KV cache grows with prompt length. LabPilot sends long
  prompts (retrieved code chunks + paper text), which is the worst case. Windows
  itself uses 3–4GB of the system RAM before anything else starts.
- **Docker Desktop (Step 3) will feel heavy.** It runs through WSL2, which takes
  a large share of 8GB. It will work, but expect slow image builds. Close other
  programs while building.
- All model inference — base models and the fine-tuned model — happens on hosted
  platforms. Nothing runs on this machine.

### Activate the virtual environment
```bash
source .venv/Scripts/activate
```

### Recreating the venv — important gotcha
Two Python versions are installed on this machine, and **plain `python`
resolves to 3.10**, not 3.13, because Python310 comes first on PATH. Always
name the version explicitly:

```bash
py -3.13 -m venv .venv
```

Verify with `python --version` **after** activating — it must say 3.13.
(`py --version` reports the launcher's default and is not a reliable check.)

### Install dependencies
```bash
pip install -r requirements.txt
```

### Environment variables
Copy `.env.example` to `.env` and fill in real values.

| Variable | Used for | Where to get it |
|---|---|---|
| **`CLINE_API_KEY`** | **Generator tier 1 — `z-ai/glm-5.3-flash`, FREE** | app.cline.bot → Settings → API Keys — no card. Free models consume **zero credits**, proven against a paid control. Only 2 of Cline's 6 free models answer the API; the quota is published nowhere and Cline sends **no rate-limit headers**. Added 2026-09-13 |
| `GOOGLE_API_KEY` | Generators, embedder, and the top 4 rerank tiers | aistudio.google.com/api-keys — **not the original account**; that one is restricted (see [Platform Accounts](../llm/platform-accounts.md#google-ai-studio--the-account-restriction-of-2026-08-11)) |
| **`GOOGLE_API_KEY_2`** | **A THIRD account — a second QUOTA, not a spare key** | Google bills per project per model, so this doubles EVERY Google budget: 20/day per Flash, 500 per Flash-Lite, 14,400 per Gemma, 1,000 embed requests. Added 2026-09-11 |
| **`GOOGLE_API_KEY_3`** | **A THIRD Google account — a third QUOTA** | Same idea as key 2: its own allowance of every model, and its own minute room (key × model). Proven live 2026-10-22: it accepted a 14,800-token prompt on Gemma 4 31B at the same moment as the other keys. **Do not add a fourth**: several accounts behind one VPN exit is the pattern that got an account flagged on 2026-08-11. The GitHub secret must be created by hand. Added 2026-10-22 |
| `MISTRAL_API_KEY` | Generator tiers 4, 5, 7, 9, **embedder primary** | console.mistral.ai — phone verification, no card |
| `OPENROUTER_API_KEY` | Generator tiers 6 + 8 | openrouter.ai/keys |
| `COHERE_API_KEY` | **Reranker tier 1**, embedder last resort | dashboard.cohere.com — trial key, no card |
| `VOYAGE_API_KEY` | **Reranker tier 2** — 200M free rerank tokens, one-time | dash.voyageai.com — no card |
| `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` | Reranker t3, embedder t4, generator t7 | dash.cloudflare.com — token needs **both** `Workers AI - Read` and `Workers AI - Edit`. The **account ID goes in the URL path**, which is why this is the only provider needing two variables |
| **`DATABASE_URL`** | **The pgvector store (slice 4)** | Supabase → Connect → **Session pooler**. Port **5432**, never 6543 — transaction mode rejects the prepared statements psycopg3 uses. User is `postgres.<project-ref>`, not `postgres`. The **direct** connection is IPv6-only and does not resolve from here |
| ~~`CEREBRAS_API_KEY`~~ | **Dead** — the API now requires a card (`402`) | — |
| ~~`MODAL_API_KEY`~~ | No longer a chain tier. Step 4 only, for serving the fine-tuned model | modal.com |

`GOOGLE_API_KEY` is deliberately named to match what the official
`google-genai` SDK reads automatically, in case we migrate off `requests` later.

**Required OpenRouter setting:** enable *"Allow free endpoints that train on
request data"*, or every `:free` model returns an error.

