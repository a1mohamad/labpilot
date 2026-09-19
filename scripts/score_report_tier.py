"""Can a CHEAP tier write the report, or does it really need a 20/day model?

Slice 8 job 9. CLAUDE.md section 11.9 challenges its own rule that
`explain_divergence` must have the strongest tier, and the challenge has real
support: session 10 measured model strength OUT as a cause of coverage, blind
spots are per-model and disjoint rather than better-and-worse, and in slice 6
the cheapest tier beat every purpose-built cross-encoder.

But the honest gap is this: **the lean REPORT template has never once been
run on a cheap tier.** Every report number in the project came from
`gemini-3.6-flash` or `gemini-3.5-flash`, both 20 requests a day.

    PYTHONPATH=. python scripts/score_report_tier.py flashlite

Stuffed, so retrieval is not a variable and the answer is comparable with the
saved 2026-08-17 baselines. One request per tier.

If a 500/day tier scores near the recorded 13 of 19, reports stop being
capped at roughly twenty a day - which is the single biggest throughput
change available to this project.
"""

from __future__ import annotations

import dataclasses
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from labpilot.ingest import chunk_file
from labpilot.llm import (
    CLINE_GLM_5_3_FLASH,
    CLINE_LAGUNA_S_2_1,
    GEMINI_3_1_FLASH_LITE,
    GEMINI_3_5_FLASH,
    GEMINI_3_5_FLASH_LITE,
    GEMMA_4_31B,
)
from labpilot.prompts import (
    REPORT,
    REPORT_MAX_TOKENS,
    build_prompt,
    find_citations,
    resolve,
)
from labpilot.tokens import estimate_tokens

SAMPLES = Path("data/samples/quora_siamese")
QUESTION = "Compare these and explain why the results diverge."

TIERS = {
    # THE CHEAPEST TIER THERE IS. Cline's free models were proven on
    # 2026-09-13 to consume ZERO credits against a paid control that deducted
    # instantly, so if either of these can write the report, a report costs
    # nothing at all - which is a bigger win than moving from 20/day to
    # 500/day.
    "cline": CLINE_GLM_5_3_FLASH,
    "laguna": CLINE_LAGUNA_S_2_1,
    "flashlite": GEMINI_3_5_FLASH_LITE,
    "flashlite31": GEMINI_3_1_FLASH_LITE,
    # 14,400 a day, and almost certainly REFUSED before it is sent: its
    # per-minute input ceiling is 16,000 tokens and a stuffed report is about
    # 26,000. Included so the refusal is measured rather than assumed.
    "gemma": GEMMA_4_31B,
    # The 20/day control. Only run this to re-establish the baseline.
    "flash35": GEMINI_3_5_FLASH,
}


def main(name: str) -> int:
    load_dotenv(".env")
    provider = TIERS[name]

    chunks = tuple(
        chunk_file(SAMPLES / "A_paper.md", side="A", artifact_id="A")
    ) + tuple(chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="B"))
    prompt = build_prompt(chunks, chunks, question=QUESTION, instructions=REPORT)
    print(
        f"{provider.name}: {len(chunks)} chunks stuffed, "
        f"~{estimate_tokens(prompt)} prompt tokens"
    )

    # MEDIUM, not HIGH, and only where the field exists. Measured 2026-08-17
    # on an identical prompt: HIGH spent 93% of a 32,000 budget on thoughts
    # and returned a TRUNCATED report, while MEDIUM finished and wrote 2.5x
    # more of it. Cline is an OpenAI-shape provider with no `thinking` field -
    # its reasoning knob is `reasoning.effort` in extra_body, and it is
    # already set in the registry, where it CAPS runaway reasoning rather
    # than raising it.
    tuned = (
        dataclasses.replace(provider, thinking="MEDIUM")
        if hasattr(provider, "thinking")
        else provider
    )

    started = time.time()
    result = tuned.complete(prompt, max_tokens=REPORT_MAX_TOKENS)
    elapsed = time.time() - started

    # find_citations returns (chunk_id, quote) PAIRS; resolve() is what
    # turns a pair into a real file and line, and a pair that will not
    # resolve is the anti-hallucination signal - the model pointed at
    # something that is not in what we sent.
    citations = find_citations(result.text)
    resolved = sum(1 for cid, quote in citations if resolve(cid, quote, chunks))
    stamp = time.strftime("%Y-%m-%d_%H-%M")
    out = Path("artifacts/slice8/runs") / f"report_{name}_{stamp}.md"
    out.write_text(
        f"# {provider.name}\n\n"
        f"- finish_reason: {result.finish_reason}\n"
        f"- seconds: {elapsed:.1f}\n"
        f"- characters: {len(result.text)}\n"
        f"- citations written: {len(citations)}, resolved: {resolved}\n\n"
        f"---\n\n{result.text}\n",
        encoding="utf-8",
    )
    print(
        f"  {result.finish_reason}  {elapsed:.1f}s  {len(result.text)} chars  "
        f"citations {resolved}/{len(citations)}\n  -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
