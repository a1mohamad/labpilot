# ruff: noqa: E501, B905, E741, E402, B007
"""The accuracy bench: every candidate model on every task, scored on labelled cases.

    python -m scripts.routing.bench r1 all                 # round 1: about half the cases
    python -m scripts.routing.bench r1 g35,th              # only some lanes
    python -m scripts.routing.bench r1 all gate,plan       # only some tasks
    python -m scripts.routing.bench r1 lr all "GLM-5.3 Flash"   # only some models
    python -m scripts.routing.analyze_bench plan           # choose round 2 finalists
    python -m scripts.routing.bench r2 all                 # round 2: the rest, finalists only

SPENDS REAL QUOTA: about 1,300 calls for a full round 1. Run collect_data.py once
before the first run. The network is checked first (the exit ISP and a Google
probe); a bad exit stops the run.

Each candidate MODEL FAMILY runs each task it may serve, with the PRODUCT prompts
and readers, ALONE (a chain of its own tiers only, no fallback), with the product
retry rule (1 s and 3 s). One JSON line per (round, task, model, case) is
appended to artifacts/routing-bench/logs/bench.jsonl: score 0..1, seconds, ok.
A case already in the log is not run again, so a stopped run can be started
again. A case refused for QUOTA is marked "limited" and counts neither way;
delete such lines to measure them again.

The answer keys (bench_keys.py and the files in data/) were written BEFORE any
model was scored on them. A regex key is a screen: read the best and the worst
answers of each task by hand before trusting a ranking.

Lanes (one provider account each) run at the same time; inside one lane the
calls run one after another, paced by the provider's own limits (_paced below).
To add a model: add it to F below (strength, lane, its tiers).
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path

from scripts.routing._common import DATA, LOGS, check_network, load_env

load_env()

import labpilot.api.tool_calls as tool_calls  # noqa: E402
import labpilot.llm.chain as chain_mod  # noqa: E402
from labpilot.api.file_parts import FileParts  # noqa: E402
from labpilot.ingest import chunk_bytes  # noqa: E402
from labpilot.llm import AllFreeTiersExhausted, LLMClient, LLMError  # noqa: E402
from labpilot.llm import registry as R  # noqa: E402
from labpilot.llm.base import HTTPProvider  # noqa: E402
from labpilot.tokens import estimate_tokens  # noqa: E402
from scripts.routing import bench_keys as K  # noqa: E402

ST9 = DATA
sys.path.insert(0, str(DATA))
import gold7 as G7  # noqa: E402
import keys9 as K9  # noqa: E402
import m28_pairs as M28  # noqa: E402
import planner_heldout as PH  # noqa: E402
import planner_questions as PQ  # noqa: E402

LOG = LOGS / "bench.jsonl"
LOCK = threading.Lock()

# ---------------------------------------------------------------- pacing
# Sequential inside one account; the measured rest between calls; the chain's own
# skip-when-busy is turned off (a single model is measured alone, so a skip
# would be a failure of the bench, not of the model).
tool_calls.CALLS_AT_ONCE = 1
chain_mod.TURN_WAIT_MAX = 30.0
chain_mod.book = lambda *a, **k: 0.0
_last: dict[str, float] = {}
_acct_lock: dict[str, threading.Lock] = {}
_orig_complete = HTTPProvider.complete
# Per account or pool: the calls of one item run on helper threads, so the state
# is kept by pool (one lane uses its own pools, one item at a time).
STATE: dict[str, dict] = {}


def _state(key):
    return STATE.setdefault(
        key, {"secs": 0.0, "limited": False, "network": False, "last": ""}
    )


def _gap(p) -> float:
    if p.api_key_env.startswith("LITEROUTER"):
        return 9.5
    rpm = getattr(p, "requests_per_minute", None)
    if rpm:
        return 60.0 / rpm + 0.5
    return 0.0


def _paced(self, prompt, **kw):
    # Google and Mistral limit each (key, model); the gateways limit the account.
    key = (
        self.quota_pool
        if self.api_key_env.startswith(("GOOGLE", "MISTRAL"))
        else self.api_key_env
    )
    lock = _acct_lock.setdefault(key, threading.Lock())
    with lock:
        gap = _gap(self)
        if self.max_input_tokens:  # Gemma: 16K input tokens a minute for each room
            gap = max(gap, estimate_tokens(prompt) * 1.15 / self.max_input_tokens * 60)
        if self.api_key_env.startswith(
            "BAZAARLINK"
        ):  # a burst gets the account blocked
            gap = max(gap, 20.0)
        if self.api_key_env.startswith(
            "GROQ"
        ):  # 8,000 tokens a minute, prompt + answer
            gap = max(
                gap,
                (estimate_tokens(prompt) * 1.1 + kw.get("max_tokens", 1024)) / 8000 * 60
                + 1,
            )
        wait = _last.get(key, 0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        t0 = time.monotonic()
        try:
            return _orig_complete(self, prompt, **kw)
        except LLMError as e:
            st_ = _state(key)
            st_["last"] = str(e)[:240]
            text = str(e).lower()
            if (
                getattr(e, "status", None) == 429
                or "http 429" in text
                or "rate limit" in text
                or "quota" in text
                or "allocation" in text
            ):
                st_["limited"] = True
            if "request failed" in text:
                st_["network"] = True
            raise
        finally:
            _last[key] = time.monotonic()
            _state(key)["secs"] += _last[key] - t0


HTTPProvider.complete = _paced

# A call the chain gave up on (every retry failed, or a hung call cut by the
# stop) never reaches _paced as an error, and a finder then quietly carries on
# with fewer answers. So the give-ups are counted per pool, at the chain.
_orig_generate = chain_mod.LLMClient.generate


def _counted(self, *a, **k):
    pools = {
        t.quota_pool
        if t.api_key_env.startswith(("GOOGLE", "MISTRAL"))
        else t.api_key_env
        for t in self.chain
    }
    try:
        out = _orig_generate(self, *a, **k)
        for p_ in pools:
            _state(p_)["answered"] = _state(p_).get("answered", 0) + 1
        return out
    except AllFreeTiersExhausted:
        for p_ in pools:
            _state(p_)["gave_up"] = _state(p_).get("gave_up", 0) + 1
        raise


chain_mod.LLMClient.generate = _counted

# ---------------------------------------------------------------- candidates
by = {t.name: t for t in R.CHAIN}


def lr(model, name, ctx, out):
    return R._literouter(
        name=name, model=model, context_window=ctx, max_output_tokens=out
    )


def keys3(base):
    t = by[base]
    return (t, by[f"{base} (key 2)"], by[f"{base} (key 3)"])


HYDROGEN = R._gemini(name="Gemini 4 Hydrogen", model="gemini-4-hydrogen", thinking=None)
HYD3 = (HYDROGEN, *R._other_accounts(HYDROGEN))
NEW_LR = {
    "Hy4 cheap": lr("hy4-cheap:free", "Hy4 cheap (LiteRouter)", 1048576, 65536),
    "Qwen3.8 27B LR": lr(
        "qwen-3.8-27b:free", "Qwen3.8 27B (LiteRouter)", 262144, 65536
    ),
    "Qwen3.8 Flash cheap": lr(
        "qwen3.8-flash-cheap:free", "Qwen3.8 Flash cheap (LiteRouter)", 1000000, 131072
    ),
    "MiniMax M2.5": lr(
        "minimax-m2.5:free", "MiniMax M2.5 (LiteRouter)", 198000, 176947
    ),
    "MiniMax M2": lr("minimax-m2:free", "MiniMax M2 (LiteRouter)", 200000, 65536),
    "Qwen3 VL 235B": lr(
        "qwen3-vl-235b-a22b-instruct:free", "Qwen3 VL 235B (LiteRouter)", 262144, 32768
    ),
    "Qwen3 32B": lr("qwen3-32b:free", "Qwen3 32B (LiteRouter)", 131072, 16384),
    "Qwen3 30B A3B": lr(
        "qwen3-30b-a3b:free", "Qwen3 30B A3B (LiteRouter)", 40960, 16384
    ),
    "Qwen3 Coder 30B": lr(
        "qwen3-coder-30b-a3b-instruct:free",
        "Qwen3 Coder 30B (LiteRouter)",
        262144,
        65536,
    ),
    "Llama 3.3 70B": lr(
        "llama-3.3-70b-instruct-turbo:free", "Llama 3.3 70B (LiteRouter)", 131072, 16384
    ),
    "Ministral 3 14B": lr(
        "ministral-3-14b-instruct:free", "Ministral 3 14B (LiteRouter)", 131072, 16384
    ),
    "Ministral 3 8B": lr(
        "ministral-3-8b-instruct:free", "Ministral 3 8B (LiteRouter)", 262000, 16384
    ),
    "Ministral 3B LR": lr(
        "ministral-3b-2512:free", "Ministral 3B (LiteRouter)", 131072, 16384
    ),
    "Magistral Small": lr(
        "magistral-small:free", "Magistral Small (LiteRouter)", 131072, 32768
    ),
    "Hy3 LR": lr("hy3:free", "Hy3 (LiteRouter)", 262144, 65536),
}

# family: (strength, lane, tiers for most tasks, tiers when the task asks 32K out)
F: dict[str, tuple] = {
    "Gemini 3.5 Flash-Lite": (3, "g35", keys3("Gemini 3.5 Flash-Lite")),
    "Gemini 3.1 Flash-Lite": (2, "g31", keys3("Gemini 3.1 Flash-Lite")),
    "Gemma 4 26B": (2, "gemma", keys3("Gemma 4 26B A4B")),
    "Gemini 3.6 Flash": (4, "g36", keys3("Gemini 3.6 Flash")),
    "Gemini 4 Hydrogen": (5, "hyd", HYD3),
    "DeepSeek V4.1 Flash": (
        5,
        "th",
        (by["DeepSeek V4.1 Flash (Token Harbor)"],),
        (by["DeepSeek V4.1 Flash 1017 (LiteRouter)"],),
    ),
    "DeepSeek V4 Flash": (
        4,
        "th",
        (by["DeepSeek V4 Flash (Token Harbor)"],),
        (by["DeepSeek V4 Flash (LiteRouter)"],),
    ),
    "MiMo V2.6 Flash": (4, "th", (by["MiMo V2.6 Flash (Token Harbor)"],)),
    "MiMo V2.5": (4, "th", (by["MiMo V2.5 (Token Harbor)"],)),
    "GLM-5.3 Flash": (4, "lr", (by["GLM-5.3 Flash (LiteRouter)"],)),
    "DeepSeek V4 Pro": (4, "lr", (by["DeepSeek V4 Pro 0813 (LiteRouter)"],)),
    "MiniMax M3.1 Flash": (5, "lr", (by["MiniMax M3.1 Flash (LiteRouter)"],)),
    "MiniMax M2.7": (3, "lr", (by["MiniMax M2.7 (LiteRouter)"],)),
    "DeepSeek V3.2": (2, "lr", (by["DeepSeek V3.2 (LiteRouter)"],)),
    "Hy4": (5, "orca", (by["Hy4 preview (OrcaRouter)"],), (NEW_LR["Hy4 cheap"],)),
    "Ling 3.1 Flash": (5, "rq", (by["Ling 3.1 Flash (Requesty)"],)),
    "Nemotron 3 Ultra": (3, "kilo", (by["Nemotron 3 Ultra (Kilo)"],)),
    "Nemotron 3.5 Lightning": (2, "kilo", (by["Nemotron 3.5 Lightning (Kilo)"],)),
    "North Mini Code": (1, "kilo", (by["North Mini Code (Kilo)"],)),
    "Qwen3.8 27B": (4, "cf", (by["Qwen3.8 27B"],)),
    "Qwen3.8 27B Groq": (4, "groq", (by["Qwen3.8 27B (Groq)"],)),
    "GPT-OSS 120B": (1, "groq", (by["GPT-OSS 120B (Groq)"],)),
    "GPT-OSS 20B": (1, "groq", (by["GPT-OSS 20B (Groq)"],)),
    "Qwen 3.7 Flash": (3, "bz", (by["Qwen 3.7 Flash (Bazaarlink)"],)),
    "DeepSeek V4 Flash 0731": (4, "bz", (by["DeepSeek V4 Flash 0731 (Bazaarlink)"],)),
    "Gemma 4 31B": (1, "rq", (by["Gemma 4 31B (Requesty)"],)),
    "Ministral 8B": (1, "m8", (by["Ministral 8B"],)),
    "Ministral 14B": (1, "m14", (by["Ministral 14B"],)),
    "Codestral": (1, "mcode", (by["Codestral"],)),
    "Qwen3 Coder Next": (1, "lr", (by["Qwen3 Coder Next (LiteRouter)"],)),
    "Qwen3 Next 80B": (1, "lr", (by["Qwen3 Next 80B (LiteRouter)"],)),
    "Qwen3.8 Flash": (4, "lr", (NEW_LR["Qwen3.8 Flash cheap"],)),
    "MiniMax M2.5": (3, "lr", (NEW_LR["MiniMax M2.5"],)),
    "MiniMax M2": (2, "lr", (NEW_LR["MiniMax M2"],)),
    "Qwen3 VL 235B": (2, "lr", (NEW_LR["Qwen3 VL 235B"],)),
    "Qwen3 32B": (1, "lr", (NEW_LR["Qwen3 32B"],)),
    "Qwen3 30B A3B": (1, "lr", (NEW_LR["Qwen3 30B A3B"],)),
    "Qwen3 Coder 30B": (1, "lr", (NEW_LR["Qwen3 Coder 30B"],)),
    "Llama 3.3 70B": (1, "lr", (NEW_LR["Llama 3.3 70B"],)),
    "Ministral 3 14B": (1, "lr", (NEW_LR["Ministral 3 14B"],)),
    "Hy3": (3, "lr", (NEW_LR["Hy3 LR"],)),
    **{
        f"Gemma 26B {n}": (2, "rw", (by[f"Gemma 4 26B A4B {n} (Routeway)"],))
        for n in ("Moonlight", "Darksoul", "Chimerax", "Luminous", "MeroMero", "Musica")
    },
}
SCARCE = {"Gemini 3.6 Flash", "Gemini 4 Hydrogen"}

# task: (min strength in the bench, prompt tokens, max_tokens, reads files)
TASKS = {
    "gate": (1, 1500, 3000, False),
    "fresh": (1, 300, 1000, False),
    "rewrite": (1, 1500, 3000, False),
    "summary": (1, 13000, 4000, False),
    "respond_chat": (1, 1000, 8000, False),
    "merge": (1, 3000, 4000, False),
    "plan": (3, 14500, 4000, False),
    "judge": (2, 12000, 12000, False),
    "claims": (3, 3000, 6000, False),
    "trace": (2, 4000, 12000, False),
    "scan": (3, 23000, 8000, False),
    "audit": (4, 28000, 12000, True),
    "checklist": (3, 4000, 6000, False),
    "checklist_audit": (4, 28000, 16000, True),
    "method": (4, 25000, 12000, True),
    "concept": (4, 25000, 12000, True),
    "skeptic": (4, 31000, 8000, True),
    "respond_one": (3, 31000, 16000, True),
    "respond_two": (4, 31000, 32000, True),
}


def fits(t, prompt, out):
    if out > t.max_output_tokens:
        return False
    if prompt * 1.1 + out > t.context_window:
        return False
    if t.max_input_tokens and prompt * 1.1 > t.max_input_tokens:
        return False
    return True


def tiers_for(family, task):
    s, lane, tiers, *big = F[family]
    mn, p, out, files = TASKS[task]
    if s < mn or (family in SCARCE and not files):
        return None
    for cand in (tiers, *(big or [])):
        if all(fits(t, p, out) for t in cand):
            return cand
    return None


def client(tiers, stop):
    return LLMClient(
        chain=tuple(tiers),
        retry_delays=(1.0, 3.0),
        call_stop=stop,
        total_budget=stop * 2 + 30,
        max_rejected_answers=1,
    )


# ---------------------------------------------------------------- inputs
def chunks_of(path: Path, side: str, root: Path | None = None, aid: str = "x"):
    source = path.relative_to(root).as_posix() if root else path.name
    return list(
        chunk_bytes(path.read_bytes(), source=source, side=side, artifact_id=aid)
    )


def case_parts(case, side):
    info = {
        "quora": (
            [ST9 / "cases/quora/A_paper.md"],
            [ST9 / "cases/quora/B_train.py"],
            ST9 / "cases/quora",
        ),
        "adam": (
            [ST9 / "cases/adam/A_adam_paper.pdf"],
            [ST9 / "cases/adam/B/adam.py"],
            ST9 / "cases/adam/B",
        ),
        "otp": (
            [ST9 / "cases/otp/A_rfc_hotp_totp.txt"],
            [
                ST9 / "cases/otp/B/otp.go",
                ST9 / "cases/otp/B/hotp/hotp.go",
                ST9 / "cases/otp/B/totp/totp.go",
            ],
            ST9 / "cases/otp/B",
        ),
    }[case]
    files = info[0] if side == "A" else info[1]
    out = []
    for f in files:
        out += chunks_of(f, side, None if side == "A" else info[2], f"{side}-{case}")
    return out


SUMMARIES9 = json.loads((DATA / "summaries9.json").read_text(encoding="utf-8"))
M28_SUM = json.loads((DATA / "m28_summaries.json").read_text(encoding="utf-8"))


def screen(text, pats):
    return all(re.search(p, text, re.I | re.S) for p in pats)


def keyscore(text_items, key):
    blob_items = text_items
    found, total = 0, 0
    for row in key:
        w, pats = row[1], row[-1]
        total += w
        if any(screen(b, pats) for b in blob_items):
            found += w
    return found / total if total else 0.0


# ---------------------------------------------------------------- tasks
def t_gate(cl):
    from labpilot.api.gate import make_gate

    g = make_gate(cl)
    for pid, kind, a, b, ok in M28.PAIRS:
        yield (
            pid,
            lambda a=a, b=b, ok=ok, kind=kind: (
                lambda v: (
                    1.0
                    if v in ok
                    else (0.0 if not (kind == "match" and v == "NONE") else -1.0)
                )
            )(g(M28_SUM[a]["summary"], M28_SUM[b]["summary"]).verdict),
        )


def t_summary(cl):
    from labpilot.prompts import (
        SUMMARY_MAX_TOKENS,
        build_summary_prompt,
    )

    src = {
        "quora_paper": case_parts("quora", "A"),
        "quora_code": case_parts("quora", "B"),
        "adam_code": case_parts("adam", "B"),
        "otp_code": case_parts("otp", "B"),
    }
    for name, chunks in src.items():

        def run(name=name, chunks=chunks):
            parts = [f"{c.header}\n{c.text}" for c in chunks]
            text = cl.generate(
                build_summary_prompt(parts), max_tokens=SUMMARY_MAX_TOKENS
            ).text
            pts = sum(bool(re.search(p, text, re.I)) for p in K.SUMMARY[name]) / len(
                K.SUMMARY[name]
            )
            return pts * (0.5 if len(text.split()) > 220 else 1.0), text[:300]

        yield name, run


def t_rewrite(cl):
    from labpilot.api.followups import make_rewriter

    rw = make_rewriter(cl)
    for i, (q, hist, last, pats) in enumerate(K.REWRITE):

        def run(q=q, hist=hist, last=last, pats=pats):
            out = rw(q, hist, last)
            return (1.0 if screen(out, pats) and "\n" not in out.strip() else 0.0), out

        yield f"r{i}", run


def t_fresh(cl):
    from labpilot.prompts import FRESH_MAX_TOKENS
    from labpilot.prompts.fresh import build_fresh_claim_prompt

    for i, (q, pats) in enumerate(K.FRESH):

        def run(q=q, pats=pats):
            out = cl.generate(
                build_fresh_claim_prompt(q), max_tokens=FRESH_MAX_TOKENS
            ).text.strip()
            ok = (
                screen(out, pats)
                and "?" not in out
                and len(out) < 400
                and out.count("\n") == 0
            )
            return (1.0 if ok else 0.0), out

        yield f"f{i}", run


def t_chat(cl):
    from labpilot.prompts import build_chat_prompt

    for i, (q, pats, cap) in enumerate(K.CHAT):

        def run(q=q, pats=pats, cap=cap):
            out = cl.generate(build_chat_prompt(q), max_tokens=8000).text
            return (1.0 if screen(out, pats) and len(out) <= cap else 0.0), out[:200]

        yield f"c{i}", run


# planner: the adam pair, headers built from the files (the database copy is gone)
def _planner_patch():
    import labpilot.api.planning as P
    from labpilot.prompts import OPENING_CHARS
    from labpilot.store.contracts import StoredHeader

    heads = {}
    for side in "AB":
        heads[f"{side}-adam"] = [
            StoredHeader(
                chunk_index=c.chunk_index,
                header=c.header,
                source=c.source,
                start_line=c.start_line,
                end_line=c.end_line,
                opening=(
                    c.text[:OPENING_CHARS]
                    if "part " not in c.header or "part 1/" in c.header
                    else ""
                ),
            )
            for c in case_parts("adam", side)
        ]
    P.read_headers = lambda conn, aid, opening_chars=0: heads[aid]
    return P


PLAN_Q = [
    q for q in PQ.Q if q[0] in ("a01", "a05", "a09", "n01", "n02", "n03", "n04")
] + PH.Q[:9]


def t_plan(cl):
    P = _planner_patch()
    from labpilot.agent import present_sides
    from labpilot.agent.plan_check import check_plan

    planner = P.make_planner(None, cl)
    sides = present_sides("A-adam", "B-adam")
    for row in PLAN_Q:
        qid, q, ask, about, files, fresh = row

        def run(q=q, ask=ask, about=about, files=files, fresh=fresh):
            plan = check_plan(planner(q, "A-adam", "B-adam"), q, sides)
            got = (bool(plan.ask), plan.about, plan.files, plan.fresh)
            want = (ask, about, files, fresh)
            pairs = [(g, w) for g, w in zip(got, want) if w is not None]
            return sum(g == w for g, w in pairs) / len(pairs), str(got)

        yield qid, run


def t_claims(cl):
    import labpilot.api.claims as C
    from labpilot.agent import read_claims

    parts = [f"{c.header}\n{c.text}" for c in case_parts("quora", "A")]
    sources = [c.header or c.source for c in case_parts("quora", "A")]
    from labpilot.agent import CLAIMS_TOOL_NAME, claims_schema
    from labpilot.llm import Tool
    from labpilot.prompts.claims import (
        CLAIMS_MAX_TOKENS,
        build_claims_prompt,
        claims_groups,
    )

    tool = Tool(
        name=CLAIMS_TOOL_NAME,
        description=C.TOOL_DESCRIPTION,
        parameters=claims_schema(),
    )

    def run():
        got = []
        for ids in claims_groups(parts):
            ps, ss = [parts[i] for i in ids], [sources[i] for i in ids]
            try:
                res = cl.generate(
                    build_claims_prompt(ps),
                    max_tokens=CLAIMS_MAX_TOKENS,
                    tool=tool,
                    problem_with=lambda r, ss=ss, ps=ps: C._claims_problem(
                        r, sources=ss, texts=ps
                    ),
                )
                got += [
                    {"text": c.text, "quote": c.quote}
                    for c in read_claims(res.arguments, ss, ps)
                ]
            except AllFreeTiersExhausted:
                pass
        cov = G7.cover(got)
        mm, m = len(cov["covered_mismatch"]), len(cov["covered_match"])
        return (2 * mm + m) / (
            2 * len(G7.MISMATCH_IDS) + len(G7.MATCH_IDS)
        ), f"{len(got)} claims, mm {mm}, m {m}"

    yield "quora", run


def t_audit(cl):
    from labpilot.api.difference_audit import run_audit

    b = FileParts.of(case_parts("quora", "B"))
    facts = [row[0] for row in G7.GOLD.values()]
    bad = {row[0] for row in G7.GOLD.values() if row[1] == "mismatch"}

    def run():
        found, answered = run_audit(cl, facts, b)
        if not answered:
            raise AllFreeTiersExhausted([])
        flagged = {d.fact for d in found}
        right = sum((f in flagged) == (f in bad) for f in facts)
        return right / len(facts), f"flagged {len(flagged)}, right {right}/32"

    yield "quora32", run


def _scan_ref(case):
    if case == "adam":
        return "\n\n".join(f"{c.header}\n{c.text}" for c in case_parts("adam", "A"))
    claims = json.loads((DATA / f"claims_{case}.json").read_text(encoding="utf-8"))
    rows = claims if isinstance(claims, list) else claims.get("claims", [])
    return "\n".join(f"- {c['text'] if isinstance(c, dict) else c}" for c in rows)


def t_scan(cl):
    from labpilot.api.difference_scan import run_scan

    for case in ("adam", "otp"):

        def run(case=case):
            found, answered = run_scan(
                cl, _scan_ref(case), FileParts.of(case_parts(case, "B"))
            )
            if not answered:
                raise AllFreeTiersExhausted([])
            items = [f"{d.text} {d.quote}" for d in found]
            return keyscore(
                items, K9.FM_SILENT[case] + K9.FM_DIFFERS[case]
            ), f"{len(found)} items"

        yield case, run


def _hunt_task(cl, hunt_name, cases, key):
    from labpilot.api.bug_hunt import _hunt
    from labpilot.prompts import HUNTS

    hunt = {"trace": HUNTS[0], "method": HUNTS[1], "concept": HUNTS[2]}[hunt_name]
    for case in cases:

        def run(case=case):
            parts = FileParts.of(case_parts(case, "B"))
            items, answered = [], False
            for g in parts.groups(hunt.group_tokens, by_file=hunt.by_file):
                got = _hunt(cl, hunt, g, SUMMARIES9[case])
                if got is not None:
                    answered = True
                    items += [f"{b.text} {b.quote}" for b in got]
            if not answered:
                raise AllFreeTiersExhausted([])
            return keyscore(items, key(case)), f"{len(items)} suspects"

        yield case, run


def t_trace(cl):
    yield from _hunt_task(cl, "trace", ("adam", "otp"), lambda c: K9.FB[c])


def t_method(cl):
    yield from _hunt_task(cl, "method", ("quora", "adam", "otp"), lambda c: K9.FB[c])


def t_concept(cl):
    yield from _hunt_task(
        cl, "concept", ("quora", "adam", "otp"), lambda c: K9.CONCEPT[c]
    )


FIXED = None  # a fixed strong client for the other half of the checklist pair


def _fixed():
    # the other half of the checklist pair: a strong model on parallel-call routes
    return client(
        (by["DeepSeek V4.1 Flash (Token Harbor)"], *keys3("Gemini 3.5 Flash-Lite")), 240
    )


CHECKLIST_CACHE = DATA / "fixed_checklists.json"


def _checklist_for(cl, case):
    from labpilot.agent import merge_obligations
    from labpilot.api.bug_hunt import _checklist
    from labpilot.prompts import CHECKLISTS

    parts = FileParts.of(case_parts(case, "B"))
    return merge_obligations(
        [_checklist(cl, ins, SUMMARIES9[case], parts) for ins in CHECKLISTS]
    )


def _audit_with(cl, case, obligations):
    from labpilot.api.bug_hunt import _audit
    from labpilot.prompts import WHOLE_GROUP_TOKENS

    parts = FileParts.of(case_parts(case, "B"))
    items, answered = [], False
    for g in parts.groups(WHOLE_GROUP_TOKENS, by_file=True):
        got = _audit(cl, obligations, g)
        if got is not None:
            answered = True
            items += [f"{b.text} {b.quote}" for b in got]
    return items, answered


def t_checklist(cl):
    for case in ("adam", "otp"):

        def run(case=case):
            obl = _checklist_for(cl, case)
            if not obl:
                raise AllFreeTiersExhausted([])
            items, _ = _audit_with(_fixed(), case, obl)
            return keyscore(
                items, K9.CONCEPT[case] + K9.FB[case]
            ), f"{len(obl)} obligations"

        yield case, run


def t_checklist_audit(cl):
    cache = json.loads(CHECKLIST_CACHE.read_text()) if CHECKLIST_CACHE.exists() else {}
    for case in ("adam", "otp"):

        def run(case=case):
            if not cache.get(case):
                made = list(_checklist_for(_fixed(), case))
                if not made:
                    raise RuntimeError("BENCH: the fixed checklist could not be made")
                cache[case] = made
                CHECKLIST_CACHE.write_text(json.dumps(cache))
            items, answered = _audit_with(cl, case, tuple(cache[case]))
            if not answered:
                raise AllFreeTiersExhausted([])
            return keyscore(
                items, K9.CONCEPT[case] + K9.FB[case]
            ), f"{len(items)} defects"

        yield case, run


def t_skeptic(cl):
    import fb_gold

    from labpilot.agent import Bug
    from labpilot.api.bug_skeptic import judge_suspects

    pool = json.loads((DATA / "fb_pool.json").read_text(encoding="utf-8"))
    for case in ("quora", "adam", "otp"):

        def run(case=case):
            parts = FileParts.of(case_parts(case, "B"))
            src = list(parts.sources)
            suspects = [
                Bug(
                    kind=s["kind"],
                    text=s["text"],
                    source=src[s["part"]] if s["part"] < len(src) else src[0],
                    quote=s["quote"],
                    severity=s.get("severity", "high"),
                )
                for s in pool[case]
            ]
            gold = fb_gold.GOLD[case]
            kept = judge_suspects(parts, suspects, cl)
            kept_text = {b.text for b in kept}
            r = [s for s, g in zip(suspects, gold) if g == "R"]
            f = [s for s, g in zip(suspects, gold) if g == "F"]
            kr = sum(s.text in kept_text for s in r) / max(1, len(r))
            rf = sum(s.text not in kept_text for s in f) / max(1, len(f))
            return 0.6 * kr + 0.4 * rf, f"real kept {kr:.2f}, false removed {rf:.2f}"

        yield case, run


def _judge_items(case):
    """Scan items of slice 9 that match one key item (real) or a trap (false)."""
    from labpilot.agent import Difference

    rows = [
        json.loads(l)
        for l in (DATA / "fm_items.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    rows = [r for r in rows if r.get("case") == case]
    key = K9.FM_SILENT[case] + K9.FM_DIFFERS[case]
    out, seen = [], set()
    for r in rows:
        for it in r.get("items", []):
            blob = f"{it.get('text', '')} {it.get('quote', '')}"
            hits = [k[0] for k in key if screen(blob, k[-1])]
            trap = any(screen(blob, t[-1]) for t in K9.TRAPS.get(case, []))
            if (len(hits) == 1 or trap) and it.get("text") not in seen:
                seen.add(it.get("text"))
                out.append(
                    (
                        Difference(
                            kind=it.get("kind", "B differs")
                            if it.get("kind")
                            in ("B differs", "A silent", "B leaves out")
                            else "B differs",
                            text=it["text"],
                            source=it.get("source", ""),
                            quote=it.get("quote", ""),
                        ),
                        "trap" if trap else hits[0],
                    )
                )
    return out


def t_judge(cl):
    from labpilot.api.difference_review import judge

    for case in ("quora", "otp"):

        def run(case=case):
            items = _judge_items(case)[:30]
            kept = judge(
                cl,
                [d for d, _ in items],
                FileParts.of(case_parts(case, "B")),
                _scan_ref(case)
                if case != "quora"
                else "\n\n".join(
                    f"{c.header}\n{c.text}" for c in case_parts("quora", "A")
                ),
            )
            kept_text = {d.text for d in kept if not getattr(d, "unclear", False)}
            real = [d for d, k in items if k != "trap"]
            traps = [d for d, k in items if k == "trap"]
            kr = sum(d.text in kept_text for d in real) / max(1, len(real))
            rt = (
                sum(d.text not in kept_text for d in traps) / max(1, len(traps))
                if traps
                else 1.0
            )
            return (
                0.8 * kr + 0.2 * rt,
                f"{len(real)} real, {len(traps)} traps, kept real {kr:.2f}",
            )

        yield case, run


def t_merge(cl):
    from labpilot.api.difference_review import make_merger

    m = make_merger(cl)
    for case in ("quora", "otp", "adam"):

        def run(case=case):
            items = [(d, k) for d, k in _judge_items(case) if k != "trap"][:16]
            lines = {
                i: f'[{d.kind}] {d.text} "{d.quote[:80]}"'
                for i, (d, _) in enumerate(items)
            }
            groups = m(lines)
            same = {
                (i, j)
                for i in lines
                for j in lines
                if i < j and items[i][1] == items[j][1]
            }
            said = {
                (min(a, b), max(a, b)) for g in groups for a in g for b in g if a != b
            }
            tp = len(same & said)
            p = tp / len(said) if said else (1.0 if not same else 0.0)
            r = tp / len(same) if same else 1.0
            return (
                2 * p * r / (p + r) if p + r else 0.0
            ), f"{len(items)} lines, {len(groups)} groups, P {p:.2f} R {r:.2f}"

        yield case, run


def _respond(cl, a_chunks, b_chunks, question, files, out, reference=False):
    from labpilot.api.prompting import build_answer_prompt

    chunks = tuple(a_chunks) + tuple(b_chunks)
    prompt, _ = build_answer_prompt(
        chunks, question=question, files=files, reference=reference
    )
    return cl.generate(prompt, max_tokens=out).text


def t_respond_one(cl):
    def run():
        text = _respond(
            cl,
            [],
            case_parts("adam", "B"),
            "Summarize this and find likely bugs.",
            1,
            16000,
        )
        return keyscore([text], K9.FB["adam"]), f"{len(text)} chars"

    yield "adam", run


def t_respond_two(cl):
    def runq():
        text = _respond(
            cl,
            case_parts("quora", "A"),
            case_parts("quora", "B"),
            "Compare these and explain why the results diverge.",
            2,
            32000,
        )
        return keyscore([text], K.STORY_QUORA), f"{len(text)} chars"

    def runo():
        text = _respond(
            cl,
            case_parts("otp", "A"),
            case_parts("otp", "B"),
            "Compare these and explain why the results diverge.",
            2,
            32000,
        )
        return keyscore(
            [text], K9.FM_DIFFERS["otp"] + K9.FB["otp"]
        ), f"{len(text)} chars"

    yield "quora", runq
    yield "otp", runo


RUNNERS = {
    "gate": t_gate,
    "summary": t_summary,
    "rewrite": t_rewrite,
    "fresh": t_fresh,
    "respond_chat": t_chat,
    "plan": t_plan,
    "claims": t_claims,
    "audit": t_audit,
    "scan": t_scan,
    "trace": t_trace,
    "method": t_method,
    "concept": t_concept,
    "checklist": t_checklist,
    "checklist_audit": t_checklist_audit,
    "skeptic": t_skeptic,
    "judge": t_judge,
    "merge": t_merge,
    "respond_one": t_respond_one,
    "respond_two": t_respond_two,
}
STOP = {
    "respond_one": 600,
    "respond_two": 600,
    "audit": 240,
    "checklist_audit": 240,
    "method": 240,
    "concept": 240,
    "skeptic": 240,
    "scan": 120,
    "summary": 120,
    "judge": 180,
}


from labpilot.agent import (
    BugsError,
    ClaimsError,
    DifferencesError,
    GateError,
    PlanError,
)

MODEL_ERRORS = (GateError, PlanError, ClaimsError, DifferencesError, BugsError)
# round 1 = a screen: about half the items of each task; round 2 = the rest,
# for the models near the top of each task (successive halving)
SUBSET = {
    "gate": {"P1", "P3", "P5", "P7", "P9"},
    "fresh": {"f0", "f2", "f4", "f6", "f8", "f10"},
    "rewrite": {"r0", "r2", "r4", "r6"},
    "summary": {"quora_paper", "otp_code"},
    "respond_chat": {"c0", "c1", "c4"},
    "merge": {"otp"},
    "judge": {"otp"},
    "plan": {"a01", "a09", "n01", "n03", "h01", "h03", "h05", "h07"},
    "claims": {"quora"},
    "audit": {"quora32"},
    "scan": {"otp"},
    "trace": {"adam"},
    "method": {"quora"},
    "concept": {"otp"},
    "checklist": {"otp"},
    "checklist_audit": {"otp"},
    "skeptic": {"adam"},
    "respond_one": {"adam"},
    "respond_two": {"quora"},
}


R2PLAN_FILE = DATA / "r2_plan.json"
R2PLAN = json.loads(R2PLAN_FILE.read_text()) if R2PLAN_FILE.exists() else {}


def done_keys():
    out = set()
    if LOG.exists():
        for l in LOG.read_text(encoding="utf-8").splitlines():
            d = json.loads(l)
            out.add((d["round"], d["task"], d["family"], d["item"]))
    return out


def run_family(rnd, family, tasks):
    done = done_keys()
    for task in tasks:
        tiers = tiers_for(family, task)
        if tiers is None:
            continue
        # round 2 measures with twice the product stop, so a slow model is judged
        # by its seconds and not scored 0 for a cut call
        cl = client(tiers, STOP.get(task, 90) * (2 if rnd == "r2" else 1))
        for item, fn in RUNNERS[task](cl):
            if (rnd, task, family, item) in done:
                continue
            if rnd == "r1" and item not in SUBSET[task]:
                continue
            if rnd == "r2" and family not in R2PLAN.get(task, ()):
                continue
            # LiteRouter takes one call at a time: round 2 does not measure again the
            # items round 1 already measured for it
            if rnd == "r2" and F[family][1] == "lr" and item in SUBSET[task]:
                continue
            t0 = time.monotonic()
            score, note, ok = 0.0, "", True
            keys_ = [
                t.quota_pool
                if t.api_key_env.startswith(("GOOGLE", "MISTRAL"))
                else t.api_key_env
                for t in tiers
            ]
            for k_ in keys_:
                STATE[k_] = {
                    "secs": 0.0,
                    "limited": False,
                    "network": False,
                    "last": "",
                    "answered": 0,
                    "gave_up": 0,
                }
            try:
                got = fn()
                score, note = got if isinstance(got, tuple) else (got, "")
            except (AllFreeTiersExhausted, LLMError, *MODEL_ERRORS) as e:
                ok, note = (
                    False,
                    f"FAILED {type(e).__name__}: {str(e)[:100]} | last: "
                    + " / ".join(_state(k)["last"] for k in keys_ if _state(k)["last"]),
                )
            except Exception as e:  # a reader or bench bug: logged, the run goes on
                if str(e).startswith("BENCH"):
                    print("skip", task, family, item, e, flush=True)
                    continue
                ok, note = False, f"ERROR {type(e).__name__}: {str(e)[:200]}"
            limited = any(_state(k)["limited"] for k in keys_)
            gave_up = sum(_state(k).get("gave_up", 0) for k in keys_)
            answered = sum(_state(k).get("answered", 0) for k in keys_)
            if ok and answered == 0 and gave_up:
                ok, note = False, f"FAILED: every call gave up ({gave_up})"
            network = any(_state(k)["network"] for k in keys_)
            rec = {
                "round": rnd,
                "task": task,
                "family": family,
                "item": item,
                "score": round(float(score), 3),
                "ok": ok,
                "seconds": round(sum(_state(k)["secs"] for k in keys_), 1),
                "wall": round(time.monotonic() - t0, 1),
                # a quota refusal or a dropped connection in ANY call of the item:
                # the score is not the model's, so the analysis leaves it out
                "limited": limited,
                "network": network,
                "answered": answered,
                "gave_up": gave_up,
                "tier": tiers[0].name,
                "note": str(note)[:300],
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with LOCK:
                with open(LOG, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
            print(
                f"{family:24s} {task:15s} {item:10s} {score:5.2f} {rec['seconds']:6.1f}s {'' if ok else note[:70]}",
                flush=True,
            )


def lanes():
    out = {}
    for fam, (s, lane, *_) in F.items():
        out.setdefault(lane, []).append(fam)
    return out


if __name__ == "__main__":
    if "--no-network-check" in sys.argv:
        sys.argv.remove("--no-network-check")
    else:
        check_network()
    rnd = sys.argv[1]
    only = (
        set(sys.argv[2].split(","))
        if len(sys.argv) > 2 and sys.argv[2] != "all"
        else None
    )
    tasks = sys.argv[3].split(",") if len(sys.argv) > 3 else list(RUNNERS)
    fams = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None
    threads = []
    for lane, families in lanes().items():
        if only and lane not in only:
            continue
        fs = [f for f in families if not fams or f in fams]
        th = threading.Thread(
            target=lambda fs=fs: [run_family(rnd, f, tasks) for f in fs], name=lane
        )
        th.start()
        threads.append(th)
    for th in threads:
        th.join()
    print("BENCH DONE", flush=True)
