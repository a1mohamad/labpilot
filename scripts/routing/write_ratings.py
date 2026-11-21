"""Propose labpilot/llm/ratings.py from the registry and the speed logs.

    python -m scripts.routing.write_ratings           write proposed/ratings.py
    python -m scripts.routing.write_ratings --apply   ... and put it in labpilot/llm/

Calls no model. One row per LIVE tier of the chain: its family (the name the
bench measures it under), its strength 1-5, its seconds, its calls a day and a
penalty. Speeds come from the speed logs: for each tier the NEWEST log that
holds it wins, so a weekly speed_check.py run moves the numbers.

A new tier needs a line in FAMILY below (its strength from Artificial Analysis
v5.0.1, older scores moved to that scale, section 31.19); the script stops with
the tier's name until it has one. per_day and the penalties follow the measured
limits of each provider (sections 31.18 and 31.19).
"""

from __future__ import annotations

import shutil
import statistics as st
import subprocess
import sys

from labpilot.llm import registry as R  # noqa: E402
from scripts.routing._common import LLM, LOGS, PROPOSED, REPO, read_jsonl

# family of a tier = the name the bench used (accuracy key), and its strength
FAMILY = [  # (start of the tier name, family, strength, confidence)
    ("Gemini 3.5 Flash-Lite", "Gemini 3.5 Flash-Lite", 3, "high"),
    ("Gemini 3.1 Flash-Lite", "Gemini 3.1 Flash-Lite", 2, "medium"),
    ("Gemini 3.6 Flash", "Gemini 3.6 Flash", 4, "medium"),
    ("Gemini 3.8 Flash", "Gemini 3.8 Flash", 5, "high"),
    ("Gemini 4 Hydrogen", "Gemini 4 Hydrogen", 5, "high"),
    ("Gemma 4 26B A4B@", "Gemma 4 26B", 2, "medium"),
    ("Gemma 4 26B A4B", None, 2, "low"),  # Routeway finetunes: own family each
    ("Gemma 4 31B", "Gemma 4 31B", 1, "medium"),
    ("DeepSeek V4.1 Flash", "DeepSeek V4.1 Flash", 5, "high"),
    ("DeepSeek V4 Flash 0731", "DeepSeek V4 Flash 0731", 4, "low"),
    ("DeepSeek V4 Flash", "DeepSeek V4 Flash", 4, "medium"),
    ("DeepSeek V4 Pro", "DeepSeek V4 Pro", 4, "medium"),
    ("DeepSeek V3.2", "DeepSeek V3.2", 2, "low"),
    ("DeepSeek V3.1", "DeepSeek V3.1", 1, "low"),
    ("GLM-5.3 Flash", "GLM-5.3 Flash", 4, "high"),
    ("MiniMax M3.1 Flash", "MiniMax M3.1 Flash", 5, "high"),
    ("MiniMax M2.7", "MiniMax M2.7", 3, "low"),
    ("MiniMax M2.5", "MiniMax M2.5", 3, "low"),
    ("MiniMax M2 ", "MiniMax M2", 2, "low"),
    ("MiMo V2.6 Flash", "MiMo V2.6 Flash", 4, "high"),
    ("MiMo V2.5", "MiMo V2.5", 4, "low"),
    ("Hy4", "Hy4", 5, "high"),
    ("Hy3", "Hy3", 3, "low"),
    ("Ling 3.1 Flash", "Ling 3.1 Flash", 5, "high"),
    ("Nemotron 3 Ultra", "Nemotron 3 Ultra", 3, "high"),
    ("Nemotron 3.5 Lightning", "Nemotron 3.5 Lightning", 2, "medium"),
    ("North Mini Code", "North Mini Code", 1, "medium"),
    ("Qwen3.8 27B (Groq)", "Qwen3.8 27B Groq", 4, "high"),
    ("Qwen3.8 27B", "Qwen3.8 27B", 4, "high"),
    ("Qwen3.8 Flash", "Qwen3.8 Flash", 4, "low"),
    ("Qwen 3.7 Flash", "Qwen 3.7 Flash", 3, "low"),
    ("Qwen3 Coder Next", "Qwen3 Coder Next", 1, "low"),
    ("Qwen3 Next 80B", "Qwen3 Next 80B", 1, "low"),
    ("Qwen3 VL 235B", "Qwen3 VL 235B", 2, "low"),
    ("Qwen3 32B", "Qwen3 32B", 1, "low"),
    ("Qwen3 30B A3B", "Qwen3 30B A3B", 1, "low"),
    ("Qwen3 Coder 30B", "Qwen3 Coder 30B", 1, "low"),
    ("Llama 3.3 70B", "Llama 3.3 70B", 1, "low"),
    ("Ministral 3 14B", "Ministral 14B", 1, "low"),
    ("Ministral 3 8B", "Ministral 8B", 1, "low"),
    ("Ministral 3B", "Ministral 3B", 1, "low"),
    ("Ministral 8B", "Ministral 8B", 1, "low"),
    ("Mistral Nemo", "Ministral 8B", 1, "low"),  # it IS Ministral 8B (31.19)
    ("Ministral 14B", "Ministral 14B", 1, "low"),
    ("Codestral", "Codestral", 1, "low"),
    ("GPT-OSS 120B", "GPT-OSS 120B", 1, "high"),
    ("GPT-OSS 20B", "GPT-OSS 20B", 1, "low"),
    ("Muse Glimmer", "Muse Glimmer 30B", 2, "medium"),
]


def family_of(name: str):
    if name.split(" (key")[0] == "Gemma 4 26B A4B":
        name = "Gemma 4 26B A4B@"
    for start, fam, s, conf in FAMILY:
        if name.startswith(start):
            if fam is None:  # a Routeway Gemma finetune
                fam = "Gemma 26B " + name.split("A4B ")[1].split(" (")[0]
            return fam, s, conf
    raise SystemExit(
        f"{name!r} has no family. Add a line to FAMILY in write_ratings.py: "
        "(start of the tier name, family, strength 1-5, confidence)."
    )


PROVIDERS = (
    "GOOGLE",
    "LITEROUTER",
    "TOKEN_HARBOR",
    "KILO",
    "REQUESTY",
    "ORCAROUTER",
    "ROUTEWAY",
    "BAZAARLINK",
    "CLINE",
    "OPENROUTER",
    "GROQ",
    "CLOUDFLARE",
    "MISTRAL",
)


def provider_of(t):
    return next(p.lower() for p in PROVIDERS if t.api_key_env.startswith(p))


def per_day(p, name):  # calls a day of the POOL (31.18 B, 31.19 table 2)
    if p == "google":
        return 500 if "Flash-Lite" in name else (14_400 if "Gemma" in name else 20)
    return {
        "literouter": 100,
        "token_harbor": 130,
        "kilo": 1000,
        "requesty": 200,
        "orcarouter": 250 if "Hy4" in name else 50,
        "routeway": 200,
        "bazaarlink": 60,
        "cline": 100,
        "openrouter": 50,
        "groq": 1000,
        "cloudflare": 40,
        "mistral": 1000,
    }[p]


def penalty(p, t, valid):
    x = 1 - valid
    if getattr(t, "max_concurrent", None) == 1:
        x += 0.1
    rpm = getattr(t, "requests_per_minute", None)
    if rpm is not None:
        x += 0.3 if rpm <= 2 else 0.2 if rpm <= 5 else 0.05 if rpm <= 10 else 0.0
    if p in ("kilo", "openrouter", "bazaarlink"):
        x += 0.1  # a pool shared with other users
    if p == "cline":
        x += 0.1  # the quota is published nowhere
    if p == "cloudflare":
        x += 0.15  # neurons: a long prompt costs a large part of the day
    return round(min(1.0, x), 2)


OLD_LOGS = [  # the measurements of 2026-11-16 to 11-20 (sections 31.19 and 33)
    REPO / "artifacts/slice11-measure/results.jsonl",
    REPO / "artifacts/slice11-measure/new_models_2026-11-20.jsonl",
]


def speeds():
    """For each tier, its calls in the newest log that holds it, and that log."""
    out = {}
    for path in [*OLD_LOGS, *sorted(LOGS.glob("speed_*.jsonl"))]:
        here = {}
        for d in read_jsonl(path):
            if d.get("kind", "call") != "call" or d.get("repeat"):
                continue
            if (
                "attempt" in d
                and d.get("kind") is None
                and not d["valid"]
                and d["attempt"] < 3
            ):
                continue  # new log: keep the last attempt of a size only
            here.setdefault(d["name"], []).append(d)
        out.update({name: (calls, path) for name, calls in here.items()})
    return out


# Used only while no speed_check.py log holds the tier.
OVERRIDE = {  # (seconds, big seconds, valid share), measured outside the main log
    "Gemma 4 26B A4B": (2.5, 3.1, 0.9),  # 31.19, sittings 2 and 3
    "Gemini 4 Hydrogen": (60.0, 70.0, 0.6),  # 31.21: 29 to 117 s, 4 of 9 requests 503
    "Gemini 3.8 Flash": (257.0, 367.0, 0.6),
}


# ruff: noqa: E501  (the generated rows are formatted by ruff afterwards)
def main():
    sp = speeds()
    dead = set(R.KNOWN_DEAD)
    pools = {}
    for t in R.CHAIN:
        if t.name not in dead:
            pools[t.quota_pool] = pools.get(t.quota_pool, 0) + 1
    rows = []
    for t in R.CHAIN:
        if t.name in dead:
            continue
        fam, s, conf = family_of(t.name)
        base = t.name.replace(" (key 2)", "").replace(" (key 3)", "")
        calls, source = sp.get(base, ([], None))
        if base in OVERRIDE and source in (None, *OLD_LOGS):
            small, big, valid = OVERRIDE[base]
        else:
            good = [c for c in calls if c["valid"]]
            if not good:
                small, big, valid = 30.0, 30.0, 0.3
            else:
                small = st.median(c["seconds"] for c in good)
                bigs = [
                    c["seconds"] for c in good if c["length"] in ("4k", "long")
                ] or [small]
                big = st.median(bigs)
                sizes = {c["length"] for c in calls}
                valid = len({c["length"] for c in good}) / max(1, len(sizes))
        p = provider_of(t)
        day = per_day(p, t.name) / pools[t.quota_pool]
        rows.append(
            (
                t.name,
                fam,
                p,
                s,
                conf,
                round(small, 1),
                round(big, 1),
                round(valid, 2),
                round(day),
                per_day(p, t.name) <= 20,
                penalty(p, t, valid),
            )
        )
    lines = [
        '"""One row per live tier: what the routes need to know about it (section 33).',
        "",
        "WRITTEN BY A SCRIPT (scripts/routing/write_ratings.py) from the registry and",
        "the speed logs; to add a tier, add its family there. `family` is the name",
        "the bench measures it under.",
        "strength 1-5: Artificial Analysis v5.0.1, older scores moved to that scale",
        "(31.19). seconds: the median of the valid calls of the 5-call test; big_seconds:",
        "the 4,000 and 20,000-token calls. per_day: calls a day of its quota pool,",
        "shared by the tiers on that pool. penalty 0..1: failed calls in the test,",
        "one call at a time, a low rate a minute, a pool shared with other users.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "",
        "",
        "@dataclass(frozen=True, slots=True)",
        "class Rating:",
        "    family: str",
        "    provider: str",
        "    strength: int",
        "    confidence: str",
        "    seconds: float",
        "    big_seconds: float",
        "    valid: float",
        "    per_day: int",
        "    scarce: bool",
        "    penalty: float",
        "",
        "",
        "RATINGS: dict[str, Rating] = {",
    ]
    for r in rows:
        lines.append(
            f"    {r[0]!r}: Rating({r[1]!r}, {r[2]!r}, {r[3]}, {r[4]!r}, {r[5]}, {r[6]}, {r[7]}, {r[8]}, {r[9]}, {r[10]}),"
        )
    lines.append("}")
    target = PROPOSED / "ratings.py"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["ruff", "format", "--quiet", str(target)], check=False)
    print(f"{len(rows)} rows proposed: {target}")
    if "--apply" in sys.argv:
        shutil.copy2(target, LLM / "ratings.py")
        print(f"applied: {LLM / 'ratings.py'}  (review the diff, then run the tests)")


if __name__ == "__main__":
    main()
