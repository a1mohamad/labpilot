"""How many chunks should we SEND? The one question retrieval cannot answer.

    PYTHONPATH=. python scripts/score_topn.py 5 10 20 50
    PYTHONPATH=. python scripts/score_topn.py stuffed --model=flash

`recall@N` only ever rises with N, so retrieval can find where MORE stops
helping and never where FEWER starts. The reason to stop sending is dilution
and lost-in-the-middle, and neither term exists until a model reads the prompt:

    P(good report) ~ P(the answer is in the N) x P(the model uses it)
                          rises with N              falls with N

The left factor is a retrieval measurement and this project has made it many
times. The right one has never been measured here at all, and `VECTOR_TOP_N`
and `RERANK_TOP_N` have shipped as guesses because of it.

THE INSTRUMENT IS `quora_siamese`, and it is the only one available: it is the
only fixture in the project with `EXPECTED.md`, an answer key of 19 real
divergences with the five that carry the causal story marked. Every other
corpus can say which chunk came back; only this one can say whether the REPORT
was right.

The corpus fits the prompt budget, so production would stuff it. That is the
point - stuffing is the control, and the N runs are the same pair deliberately
cut down, so the only thing that changes is how much evidence the model got.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from labpilot.ingest import chunk_file
from labpilot.llm.registry import (
    GEMINI_3_5_FLASH,
    GEMINI_3_5_FLASH_LITE,
    GEMINI_3_6_FLASH,
)
from labpilot.prompts import (
    REPORT,
    REPORT_MAX_TOKENS,
    build_prompt,
    find_citations,
    resolve,
)
from labpilot.tokens import estimate_tokens
from scripts.score_hybrid import EMBEDDERS, embedded

SAMPLES = Path("data/samples/quora_siamese")
OUT = Path("artifacts/slice8v2/topn")
CACHE = Path(".cache/hybrid")

# The question the product itself prefills for two artifacts, verbatim. A
# different wording would be a different retrieval query AND a different task,
# and CLAUDE.md's rule is that the default prompt is versioned for exactly
# that reason.
QUESTION = "Compare these and explain why the results diverge."

MODELS = {
    "flash36": GEMINI_3_6_FLASH,
    "flash35": GEMINI_3_5_FLASH,
    "flashlite": GEMINI_3_5_FLASH_LITE,
}


def sides() -> tuple[list, list]:
    a = list(chunk_file(SAMPLES / "A_paper.md", side="A", artifact_id="A"))
    b = list(chunk_file(SAMPLES / "B_train.py", side="B", artifact_id="B"))
    return a, b


def vectors_for(chunks, tag: str, embedder, task: str) -> list:
    return embedded(embedder, [c.embed_text for c in chunks], task=task, tag=tag)


def top_n(chunks, chunk_vectors, question_vector, n: int) -> list:
    scored = sorted(
        (
            (sum(a * b for a, b in zip(question_vector, v, strict=True)), i)
            for i, v in enumerate(chunk_vectors)
        ),
        reverse=True,
    )
    # Back into corpus order once chosen. The model reads a file top to bottom
    # and so should the evidence; relevance decided WHICH chunks, not the order
    # they are presented in.
    return sorted(i for _, i in scored[:n])


def run(n: int | None, model_key: str) -> dict:
    embedder = EMBEDDERS["codestral"]
    a, b = sides()
    av = vectors_for(a, f"topn_A_{embedder.model}", embedder, "document")
    bv = vectors_for(b, f"topn_B_{embedder.model}", embedder, "document")
    qv = embedded(embedder, [QUESTION], task="query", tag=f"topn_q_{embedder.model}")[0]

    if n is None:
        chunks = tuple(a + b)
        selected = chunks
        label = "stuffed"
    else:
        keep_a = top_n(a, av, qv, n)
        keep_b = top_n(b, bv, qv, n)
        chunks = tuple(a + b)
        selected = tuple([a[i] for i in keep_a] + [b[i] for i in keep_b])
        label = f"top{n}"

    prompt = build_prompt(
        chunks,
        selected,
        question=QUESTION,
        instructions=REPORT,
        totals={"A": len(a), "B": len(b)},
    )
    provider = MODELS[model_key]
    started = time.time()
    result = provider.complete(prompt, max_tokens=REPORT_MAX_TOKENS)
    took = time.time() - started

    found = find_citations(result.text)
    resolved = [
        got for got in (resolve(cid, quote, chunks) for cid, quote in found) if got
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%H-%M")
    (OUT / f"{label}_{provider.model}_{stamp}.md").write_text(
        f"# {label} on {provider.model}\n\n"
        f"- chunks sent: {len(selected)} of {len(chunks)}\n"
        f"- prompt tokens (est): {estimate_tokens(prompt)}\n"
        f"- finish: {result.finish_reason}\n"
        f"- seconds: {took:.1f}\n"
        f"- citations: {len(resolved)} of {len(found)} resolved\n\n"
        f"---\n\n{result.text}\n",
        encoding="utf-8",
    )
    return {
        "label": label,
        "n": n,
        "model": provider.model,
        "sent": len(selected),
        "total": len(chunks),
        "prompt_tokens": estimate_tokens(prompt),
        "finish": result.finish_reason,
        "seconds": round(took, 1),
        "citations": len(found),
        "resolved": len(resolved),
        "characters": len(result.text),
    }


def main(argv: list[str]) -> int:
    load_dotenv(".env")
    model = next((a.split("=")[1] for a in argv if a.startswith("--model=")), "flash36")
    wanted = [a for a in argv[1:] if not a.startswith("--")]
    if not wanted:
        print(f"usage: {argv[0]} <N|stuffed> [...] [--model={'|'.join(MODELS)}]")
        return 2

    rows = []
    for want in wanted:
        n = None if want == "stuffed" else int(want)
        got = run(n, model)
        rows.append(got)
        print(
            f"  {got['label']:9} sent {got['sent']:3}/{got['total']:3}  "
            f"{got['prompt_tokens']:6} tok  {got['finish']:10} "
            f"{got['seconds']:5.1f}s  {got['characters']:6} chars  "
            f"cites {got['resolved']}/{got['citations']}",
            flush=True,
        )
        time.sleep(4)

    results = Path(".logs/results")
    results.mkdir(parents=True, exist_ok=True)
    (results / f"topn_{model}.json").write_text(json.dumps(rows, indent=1))
    print(f"\n  reports saved under {OUT}/ - grade them against EXPECTED.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
