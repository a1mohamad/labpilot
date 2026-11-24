# Sources and the network check

[Docs home](../README.md)

### Sources — verify before trusting
When checking whether a platform or service is free, **only two sources count**:
the provider's own pricing page, and the actual signup or deploy flow.

Blog posts, "best free GPU" lists, and credit-aggregator sites are frequently
wrong or out of date. This was proven on 2026-08-08: three platforms
(Beam, Cerebrium, Saturn Cloud) were reported as "free, no card" by such sites
and all three required a card when tested. Every claim sourced from official
documentation held true.

Also watch the wording. **"No charge" is not the same as "no card needed."**
Several platforms perform a "$0 authorization" — they take no money, but a card
is still required, so the account is still blocked.

### Network precondition — check the exit ISP before any LLM work

*Added 2026-08-27, at the user's request, after the 2026-08-20 "Google is dead"
scare turned out to be the network and not the provider.*

The user works through a VPN, so **the exit IP and ISP change between sessions
and even between reconnects**. Some exits are refused by Google. That makes the
network a **precondition of the work**, not a background detail — a refused exit
looks exactly like a dead provider in the logs, and the whole of session 12 was
spent writing "Google is blocked" into this file when Google was fine.

**The rule, and it is deliberately narrow:**

> **Before anything that calls a model — a smoke run, a live probe, a real
> report, any Google endpoint — check the exit ISP first and say it out loud.
> Never for ordinary work: reading code, writing tests, editing this file, and
> running the mocked suite all need no check.**

Claude runs the check and reports it; the user should not have to remember.

**Step 1 — which exit are we on?** Costs nothing.

```bash
curl -s https://ipinfo.io/json
```

**Step 2 — does Google actually answer?** This is the verdict. `flash-lite` is
500/day, so the probe is nearly free — and it must be a real `generateContent`.
**`GET /v1beta/models` is not a valid probe**: it returned 200 all through the
2026-08-11 account restriction, while every generation call was refused.

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent" -H "x-goog-api-key: $GOOGLE_API_KEY" -H 'Content-Type: application/json' -d '{"contents":[{"parts":[{"text":"say ok"}]}],"generationConfig":{"maxOutputTokens":2048}}'
```

| Result | Means |
|---|---|
| **200** | the exit is fine — proceed |
| **400 `FAILED_PRECONDITION`** | **the exit IP**. Switch server or tunnel mode; the code is innocent |
| **403 `PERMISSION_DENIED`** | **the account** is flagged. A different exit will not help |
| **429** | quota, not network. Flash is 20/day |

**The ISP name is a hint, never a verdict.** `AS58212 dataforest GmbH` was the
refused exit on 2026-08-20 **and** the working exit on 2026-08-27. Same ISP,
opposite outcome. Report the ISP because it is the thing the user recognises and
can act on — but decide on the probe.

**Three data points now, and they all say the same thing.** 2026-08-30 probed
`185.209.196.176`, **AS39351 31173 Services AB**, Frankfurt → **200**. So a
*second, different* ISP also works, while the first one has been both refused and
accepted. **No ISP is known-good or known-bad. Only the probe decides.**

> **When a provider looks dead, prove the network first.** It is two commands
> and no quota, and it is the difference between a real finding and twelve
> paragraphs of fiction.

