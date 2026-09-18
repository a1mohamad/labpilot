"""How many chunks should we SEND? Measured on WHOLE corpora, not slices.

    PYTHONPATH=. python scripts/score_answers.py cobra log jq --n=5,10,20,30
    PYTHONPATH=. python scripts/score_answers.py --all --n=10,20 --model=gemma31

THE QUESTION RETRIEVAL CANNOT ANSWER. `recall@N` only rises with N, so
retrieval finds where MORE stops helping and never where FEWER starts. The
reason to stop sending is that the model stops using what it is given, and
that term does not exist until a model reads the prompt.

WHY THE FIRST ATTEMPT DID NOT COUNT, and it is worth keeping. It ran on
`quora_siamese` alone - 100 chunks total - so "send 50 per side" meant sending
68% of the entire corpus. On a 1,000-chunk artifact 50 is 5%. One fixture
cannot tell those apart, and they predict opposite things:

    if the best N is flat across corpus sizes   -> it is about the COUNT
    if the best N tracks a percentage           -> it is about COVERAGE

SLICING WAS REJECTED, and the reason is not pedantry: `geo[:50]` is the first
7% of a Go library in file order, with broken references and no coherent
structure. Nobody uploads that, so a number measured on it need not transfer.
Instead this runs on THIRTEEN WHOLE CORPORA whose natural sizes already span
78 to 1,160 chunks.

THE ANSWER KEY ALREADY EXISTS. Every fixture carries ~20 questions, each with
a ground-truth file and line. So a report can be graded mechanically on any
corpus, with no hand-written EXPECTED.md:

    answered   the model gave an answer rather than "not in the context"
    cited      it produced a [B-12 "quote"] our own parser can read
    CORRECT    the citation resolves to the ground-truth FILE and LINE

The third is the measurement. The first two are how you tell a model that
stayed silent from one that answered confidently from the wrong chunk.

Chunks are chosen by the SAME path the product uses - vector search over the
cached embeddings - so this measures the pipeline and not an oracle.
"""

from __future__ import annotations

import dataclasses
import json
import math
import pickle
import re
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from labpilot.api.reranking import CHAIN as RERANK_CHAIN
from labpilot.api.services import RERANK_WINDOW
from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.llm.defaults import SAFETY_MARGIN_RATIO
from labpilot.llm.registry import (
    GEMINI_3_5_FLASH_LITE,
    GEMMA_4_26B,
    GEMMA_4_31B,
)
from labpilot.tokens import estimate_tokens
from scripts.score_hybrid import CORPORA, targets
from scripts.score_rerank import cached_vectors, dense_orders

RESULTS = Path(".logs/results")
# The listwise cache is keyed by the candidate SET (G14), so one window
# serves every value of N and a re-run of the sweep is free.
CACHE = Path(".cache/topn")
OUT = Path("artifacts/slice8v2/answers")

MODELS = {"flashlite": GEMINI_3_5_FLASH_LITE, "gemma31": GEMMA_4_31B}

# EVERY rerank tier the chain holds, keyed by a short name, IN CHAIN ORDER.
# The user's rule for this run: use whatever is alive, in the order we have -
# and keep ONE model across every corpus inside a single comparison, because
# mixing them is exactly what voided the first top-N attempt.
#
# Probed 2026-09-19: flashlite ALIVE but 429s on RPM, gemma31 HTTP 500 on ~2
# calls of 3, gemma26 answers and returns the IDENTITY order on a 3-document
# probe, voyage3 / voyage3lite / cohere / bge all ALIVE.
RERANKERS = {
    name: next(t for t in RERANK_CHAIN if getattr(t, "name", "") == label)
    for name, label in (
        ("flashlite", "Gemini 3.5 Flash-Lite"),
        ("flashlite2", "Gemini 3.5 Flash-Lite (key 2)"),
        ("flashlite31", "Gemini 3.1 Flash-Lite"),
        ("flashlite312", "Gemini 3.1 Flash-Lite (key 2)"),
        ("gemma26", "Gemma 4 26B A4B"),
        ("gemma262", "Gemma 4 26B A4B (key 2)"),
        ("gemma31", "Gemma 4 31B"),
        ("gemma312", "Gemma 4 31B (key 2)"),
        ("voyage3", "Voyage Rerank 3"),
        ("voyage3lite", "Voyage Rerank 3 Lite"),
        ("cohere", "Cohere Rerank v4 Fast"),
        ("bge", "BGE Reranker Base"),
    )
}

# The second Google account is a second QUOTA, not a spare key - Google bills
# per project per model.
SECOND_KEY = "GOOGLE_API_KEY_2"


def buckets(provider) -> tuple:
    """One model across both accounts, as a CHAIN.

    gemma answers HTTP 500 for roughly one call in three - measured in slice 6
    on both accounts, so it is Google's serving and not a key. A hand-rolled
    retry kept losing whole runs tonight; the project's own fallback loop
    already knows that a 500 is retryable and that a spent pool is skipped.
    """
    siblings = [provider]
    if provider.model.startswith("gemma"):
        other = GEMMA_4_26B if provider.model == GEMMA_4_31B.model else GEMMA_4_31B
        siblings.append(other)
    return tuple(
        t
        for tier in siblings
        for t in (
            tier,
            dataclasses.replace(
                tier,
                name=f"{tier.name} (key 2)",
                api_key_env=SECOND_KEY,
                quota_pool=f"{SECOND_KEY}:{tier.model}",
            ),
        )
    )


# A tier that cannot take the prompt cannot answer the question, and that is
# itself a result: 21k tokens disqualifies Gemma (16,000 input tokens/minute,
# 14,400 calls a day) and leaves only Gemini Flash at 20 a day. So the token
# cost of each N is reported beside its score.
GEMMA_INPUT_LIMIT = 16_000

INSTRUCTION = """You are answering questions about a codebase or document set.

Below are numbered extracts. Answer EVERY question using ONLY those extracts.

For each question give exactly one line:

    Q3: <your answer> [B-12 "an exact line copied from the extract"]

The citation is required and must be a line copied CHARACTER FOR CHARACTER
from the extract you used. If the extracts do not contain the answer, write:

    Q3: NOT IN THE EXTRACTS

Do not guess. An answer with no supporting extract is worse than admitting the
extracts do not cover it.

--- EXTRACTS
{context}

--- QUESTIONS
{questions}"""

ANSWER = re.compile(r"^\s*Q(\d+)\s*:\s*(.+)$", re.M)

# ANY reference to a chunk id counts, wherever the quote sits.
#
# THE FIRST VERSION REQUIRED THE QUOTE INSIDE THE BRACKETS - [B-12 "line"] -
# and the model sometimes writes [B-12] "line" instead. That scored a reply
# with sixteen perfectly good citations as ZERO cited, and the row read like a
# model collapsing at N=100 rather than like a regex missing a space.
#
# It is the mistake this project already made once, when gemma was recorded as
# "unable to follow the format" and the real fault was reading the front of its
# reply. Grading is allowed to be strict about SUBSTANCE and must never be
# strict about punctuation it did not need: grade() only ever reads the id, so
# the quote's position cannot change any verdict.
CITATION = re.compile(r"\[([AB]-\d+)")


def vector_orders(chunks, queries, corpus: str) -> dict:
    """Cosine order per question - the baseline both paths start from."""
    chunk_vectors = cached_vectors(corpus, "codestral-embed", "chunks", len(chunks))
    query_vectors = cached_vectors(corpus, "codestral-embed", "queries", len(queries))
    return dense_orders(queries, query_vectors, chunk_vectors)


def reranked(
    chunks, queries, corpus: str, dense: dict, tier, window: int, pace: float
) -> tuple[dict, int]:
    """`dense`, with each question's top `window` re-ordered by a reranker.

    THE POINT OF THE WHOLE RUN. Everything below `dense` is untouched, so the
    only difference between a rerank row and a vector row is the ORDER of the
    candidates - which is exactly what RERANK_TOP_N is a number about.

    Cached per (corpus, model, window) because a listwise call is keyed by the
    candidate SET: the same window serves every value of N, so the sweep costs
    ONE call per question, not one per question per N.

    A tier that declines leaves the dense order in place, which is what `skip`
    means everywhere else in this project - and it is COUNTED, because a
    decline scores exactly like vector alone and is otherwise invisible.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    tag = CACHE / f"topn_{corpus}_{tier.model.replace('/', '_')}_w{window}.pkl"
    if tag.exists():
        cached, was_declined = pickle.loads(tag.read_bytes())
        if set(cached) == {q.id for q in queries}:
            print(f"    cached, {was_declined} had declined")
            return {q.id: cached[q.id] for q in queries}, was_declined

    out, declined = {}, 0
    for i, query in enumerate(queries, 1):
        if i > 1 and pace:
            time.sleep(pace)
        candidates = [position for position, _ in dense[query.id][:window]]
        if not candidates:
            out[query.id] = dense[query.id]
            continue

        documents = [chunks[position].embed_text for position in candidates]
        ranking = None
        for attempt in range(5):
            try:
                ranking = tier.rank(query.text, documents, top_n=None)
                break
            except Exception as exc:
                print(
                    f"      {query.id} try {attempt + 1}: {str(exc)[:50]}", flush=True
                )
                time.sleep(5 + 10 * attempt)

        if ranking is None or not ranking.order:
            declined += 1
            out[query.id] = dense[query.id]
            continue

        # POSITIONS index the list we PASSED. `candidates[pos]` is the corpus
        # position; `pos` alone would name a different chunk entirely.
        head = [
            (candidates[pos], 0.0) for pos in ranking.order if pos < len(candidates)
        ]
        out[query.id] = head + list(dense[query.id][window:])
        print(f"      {i}/{len(queries)}", end="\r", flush=True)

    print(f"    reranked {len(queries)} queries, {declined} declined      ")
    tag.write_bytes(pickle.dumps((out, declined)))
    return out, declined


def chosen(
    chunks, queries, corpus: str, n: int, orders: dict | None = None
) -> list[int]:
    """The `n` chunks a multi-question report would actually be sent.

    `n` is the TOTAL number of chunks in the prompt, not a per-query top-k -
    that is the number the product spends and the one the budget constrains.

    They are taken ROUND-ROBIN across the questions: every question gives up
    its best chunk before any question gives a second. A plain "best n by
    score" would let one easy question own the whole prompt, which is the same
    starvation per-side reranking exists to prevent one layer down.
    """
    dense = orders if orders is not None else vector_orders(chunks, queries, corpus)

    keep: list[int] = []
    seen: set[int] = set()
    for rank in range(len(chunks)):
        for query in queries:
            if len(keep) >= n:
                return sorted(keep)
            order = dense[query.id]
            if rank < len(order):
                position = order[rank][0]
                if position not in seen:
                    seen.add(position)
                    keep.append(position)
    return sorted(keep)


def render(chunks, keep: list[int]) -> str:
    return "\n\n".join(
        f"[B-{i}] {chunks[i].header}\n{chunks[i].text}" for i in sorted(keep)
    )


def ask(client: LLMClient, context: str, questions: list) -> str:
    numbered = chr(10).join(f"Q{i + 1}: {q.text}" for i, q in enumerate(questions))
    prompt = INSTRUCTION.format(context=context, questions=numbered)
    # A dropped connection is not a spent quota. The chain treats a transport
    # failure as "next tier" and with four tiers a bad minute can burn all of
    # them, so the whole walk is retried rather than the call.
    for attempt in range(3):
        try:
            return client.generate(prompt, max_tokens=8192).text
        except AllFreeTiersExhausted as exc:
            print(f"      chain {attempt + 1}/3 failed: {str(exc)[:60]}", flush=True)
            time.sleep(10 + 20 * attempt)
    return ""


def grade(reply: str, chunks, queries, sent: list[int]) -> dict:
    """Answered, cited, and CORRECT - the third is the measurement.

    Correct means the citation resolves to a chunk that really holds the
    ground-truth line. A model that answers from the wrong chunk scores
    `cited` and not `correct`, which is exactly the failure a bare "did it
    answer" count would hide.
    """
    said = {int(num): text for num, text in ANSWER.findall(reply)}
    answered = cited = correct = declined = 0

    for i, query in enumerate(queries, 1):
        text = said.get(i, "")
        if not text:
            continue
        if "NOT IN THE EXTRACTS" in text.upper():
            declined += 1
            continue
        answered += 1

        marks = CITATION.findall(text)
        if not marks:
            continue
        cited += 1

        want = targets(chunks, query)
        # The chunk it cited, by our own id scheme, must be one that really
        # holds the answer line - and it must also be one we actually SENT,
        # or the model invented an id.
        got = {int(cid.split("-")[1]) for cid in marks}
        if got & want and got <= set(sent):
            correct += 1

    return {
        "asked": len(queries),
        "answered": answered,
        "declined": declined,
        "cited": cited,
        "correct": correct,
    }


def run(
    corpus: str,
    sizes: list[int],
    model_key: str,
    rerank_key: str = "",
    window: int = RERANK_WINDOW,
    pace: float = 0.0,
) -> list[dict]:
    chunks, queries = CORPORA[corpus]()
    provider = MODELS[model_key]
    client = LLMClient(chain=buckets(provider))
    rows = []

    print(f"\n=== {corpus}: {len(chunks)} chunks, {len(queries)} questions")
    print(
        f"  {'N':>4} {'share':>7} {'tokens':>8} {'gemma?':>7} "
        f"{'answered':>9} {'cited':>6} {'CORRECT':>8}"
    )

    orders = vector_orders(chunks, queries, corpus)
    rerank_declined = 0
    if rerank_key:
        tier = RERANKERS[rerank_key]
        print(f"  reranking with {tier.name}, window {window}")
        orders, rerank_declined = reranked(
            chunks, queries, corpus, orders, tier, window, pace
        )

    for n in sizes:
        if n > len(chunks):
            continue
        keep = chosen(chunks, queries, corpus, n, orders)
        context = render(chunks, keep)
        numbered = chr(10).join(f"Q{i + 1}: {q.text}" for i, q in enumerate(queries))
        tokens = estimate_tokens(
            INSTRUCTION.format(context=context, questions=numbered)
        )
        share = len(keep) / len(chunks)

        # THE MARGIN IS PART OF THE LIMIT. `_check_fits` refuses on
        # `estimate * 1.10`, not on the estimate, so a bare comparison against
        # 16,000 says "fits" and the provider then refuses locally - which the
        # first run recorded as a score of ZERO instead of as a refusal. A
        # pre-check that does not use the same arithmetic as the real check is
        # not a pre-check.
        padded = math.ceil(tokens * (1 + SAFETY_MARGIN_RATIO))
        fits = "yes" if padded <= GEMMA_INPUT_LIMIT else "NO"

        # A tier that cannot take the prompt cannot answer, and that is a
        # RESULT rather than an error: it is the cost of sending more chunks,
        # paid in which models are still available.
        if provider.max_input_tokens is not None and padded > provider.max_input_tokens:
            print(
                f"  {n:4} {share:7.0%} {tokens:8} {fits:>7} "
                f"REFUSED - over {provider.max_input_tokens} input tokens",
                flush=True,
            )
            rows.append(
                {
                    "corpus": corpus,
                    "chunks": len(chunks),
                    "n": n,
                    "sent": len(keep),
                    "share": share,
                    "rerank": rerank_key,
                    # HOW MANY QUESTIONS WERE NOT ACTUALLY RERANKED. A declined query
                    # falls back to the dense order and scores exactly like vector
                    # alone, so it is invisible in the score and would quietly drag a
                    # rerank row toward its own baseline. The smoke run declined 6 of
                    # 20 on Voyage's 3-RPM limit before pacing was added.
                    "rerank_declined": rerank_declined,
                    "tokens": tokens,
                    "fits_gemma": False,
                    "padded": padded,
                    "model": provider.model,
                    "refused": True,
                    "asked": len(queries),
                    "answered": 0,
                    "declined": 0,
                    "cited": 0,
                    "correct": 0,
                }
            )
            continue

        reply = ask(client, context, queries)
        got = grade(reply, chunks, queries, keep)

        print(
            f"  {n:4} {share:7.0%} {tokens:8} {fits:>7} "
            f"{got['answered']:9} {got['cited']:6} {got['correct']:8}",
            flush=True,
        )
        rows.append(
            {
                "corpus": corpus,
                "chunks": len(chunks),
                "n": n,
                "sent": len(keep),
                "share": share,
                "tokens": tokens,
                "fits_gemma": padded <= GEMMA_INPUT_LIMIT,
                "padded": padded,
                "model": provider.model,
                **got,
            }
        )

        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{corpus}_n{n}_{provider.model}.md").write_text(reply, encoding="utf-8")
        time.sleep(3)
    return rows


def main(argv: list[str]) -> int:
    load_dotenv(".env")
    sizes = [
        int(x)
        for x in next(
            (a.split("=")[1] for a in argv if a.startswith("--n=")), "5,10,20,30,50"
        ).split(",")
    ]
    model = next((a.split("=")[1] for a in argv if a.startswith("--model=")), "gemma31")
    rerank = next((a.split("=")[1] for a in argv if a.startswith("--rerank=")), "")
    # SECONDS BETWEEN RERANK CALLS. Not politeness - a rate-limited tier
    # that exhausts its retries DECLINES, and a declined query silently
    # scores like vector alone. Voyage is 3 RPM (21s), flash-lite 15 (4.2s).
    pace = float(next((a.split("=")[1] for a in argv if a.startswith("--pace=")), 0.0))
    window = int(
        next(
            (a.split("=")[1] for a in argv if a.startswith("--window=")),
            RERANK_WINDOW,
        )
    )
    names = (
        sorted(CORPORA)
        if "--all" in argv
        else [a for a in argv[1:] if not a.startswith("--")]
    )
    if not names:
        print(f"usage: {argv[0]} <corpus>... | --all [--n=5,10,20] [--model=gemma31]")
        return 2

    rows: list[dict] = []
    for name in names:
        try:
            rows.extend(run(name, sizes, model, rerank, window, pace))
        except SystemExit as exc:
            print(f"  {name}: skipped - {exc}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    # A RERANK run writes its own file. It is a different measurement from the
    # vector one and the point is to COMPARE them, so overwriting would destroy
    # the baseline - which is exactly how v2's 13-corpus run was nearly lost.
    suffix = f"_rerank_{rerank}_w{window}" if rerank else ""
    out = RESULTS / f"answers_{model}{suffix}.json"
    out.write_text(json.dumps(rows, indent=1))
    print()
    print(f"wrote {out}")

    print(f"\npooled over {len({r['corpus'] for r in rows})} corpora")
    print(
        f"  {'N':>4} {'corpora':>8} {'mean share':>11} {'correct/asked':>14} "
        f"{'fits gemma':>11}"
    )
    for n in sizes:
        got = [r for r in rows if r["n"] == n]
        if not got:
            continue
        rate = sum(r["correct"] for r in got) / sum(r["asked"] for r in got)
        print(
            f"  {n:4} {len(got):8} {statistics.mean(r['share'] for r in got):11.0%} "
            f"{rate:14.3f} {sum(r['fits_gemma'] for r in got):6} of {len(got)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
