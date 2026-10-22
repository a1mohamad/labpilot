"""A quick, NOT thorough test: one big call, or the same text cut into parts?

Run from the repository root:

    python -m scripts.measure_claim_sizes OUT_DIR stats
    python -m scripts.measure_claim_sizes OUT_DIR run [ENTRY ...]

It spends free model quota (about 130 calls) and writes `results.jsonl` and
`raw/<entry>__<size>.json` into OUT_DIR, so an interrupted run can be resumed.
Check the exit ISP first: the network precondition in CLAUDE.md applies.

THE QUESTION, decided before any number was seen: when a model must list EVERY
fact of a long text, does it find more when the text is cut into parts of 12K
tokens than when it gets parts of 28K, or the whole 90K at once?

THE PROXY. A real claim needs judgement, so it cannot be scored mechanically. A
named constant (NAME = 0.35) can: the true list comes from the AST. So the task
is "list every top-level CAPITAL_NAME = value, with its value and part". This
measures attention over a long input, NOT the quality of real claims.

THE DECISION RULE, written before the run:

    recall = true constants found (name AND value) / all true constants
    a gap under 0.05 is a TIE (one run each, no noise estimate)
    C  (always parts, one fixed size 12K)  if, for at least 60% of the models
       that can do the big call, recall(12K) >= best(ALL, 28K) - 0.05
    B  (a size per model) otherwise, because a bigger size is clearly better
    A  (the whole text at once) is B with the biggest size, chosen only if ALL
       beats 28K by more than 0.05

The first result (2026-10-22, 9 models) is in section 23.6 of CLAUDE.md and
DETAILS.md; the per-run rows are in docs/step2/slice7/size_test_results.jsonl.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

REPO = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")

from labpilot.ingest import chunk_file  # noqa: E402
from labpilot.llm import LLMError, Tool  # noqa: E402
from labpilot.llm import registry as R  # noqa: E402
from labpilot.llm.openai_compatible import OpenAICompatibleProvider  # noqa: E402
from labpilot.tokens import estimate_tokens  # noqa: E402

TARGET_EST = 90_000  # tokens, by our chars/3 estimate
SIZES = {"ALL": 10**9, "28K": 28_000, "12K": 12_000}
MAX_OUT = 24_000
SKIP = {"__init__.py", "registry.py"}

INSTRUCTION = """\
You are reading source code. It comes as numbered parts: [part 0], [part 1], and
so on.

List EVERY setting: a name written in CAPITAL LETTERS that is given a fixed value
(a number, a piece of text, or a short tuple) at the top level of a file. Give the
name exactly as written, the value exactly as written, and the number of the part.
Skip a name that is set from a call or from another name. Do not stop early: the
list can be long, and a missing setting is the one mistake that matters."""
CLOSING = "List every setting now."
TOOL = Tool(
    name="list_settings",
    description="List every top-level CAPITAL_NAME that has a fixed value.",
    parameters={
        "type": "object",
        "properties": {
            "settings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                        "part": {"type": "integer"},
                    },
                    "required": ["name", "value", "part"],
                },
            }
        },
        "required": ["settings"],
    },
)


def load_corpus() -> tuple[list[pathlib.Path], list]:
    files = sorted(
        path for path in (REPO / "labpilot").rglob("*.py") if path.name not in SKIP
    )
    taken, chunks, used = [], [], 0
    for path in files:
        if used >= TARGET_EST:
            break
        got = chunk_file(
            path,
            side="A",
            artifact_id="A-sizes",
            source=path.relative_to(REPO).as_posix(),
        )
        used += sum(estimate_tokens(f"{c.header}\n{c.text}") + 2 for c in got)
        chunks.extend(got)
        taken.append(path)
    return taken, chunks


def norm_value(text: object) -> str:
    text = re.sub(r"(?<=\d)_(?=\d)", "", str(text).strip())
    return text.replace("'", "").replace('"', "").replace(" ", "")


def literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and not isinstance(node.value, bytes):
        return ast.unparse(node)
    if isinstance(node, ast.UnaryOp) and isinstance(node.operand, ast.Constant):
        return ast.unparse(node)
    if (
        isinstance(node, ast.Tuple)
        and node.elts
        and all(isinstance(e, ast.Constant) for e in node.elts)
    ):
        return ast.unparse(node)
    return None


def true_constants(files: list[pathlib.Path]) -> dict[tuple[str, str], str]:
    truth: dict[tuple[str, str], str] = {}
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in tree.body:
            pairs = []
            if isinstance(node, ast.Assign):
                pairs = [(target, node.value) for target in node.targets]
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                pairs = [(node.target, node.value)]
            for target, value in pairs:
                if not isinstance(target, ast.Name):
                    continue
                if not re.fullmatch(r"[A-Z][A-Z0-9_]*", target.id):
                    continue
                shown = literal(value)
                if shown is not None:
                    key = (target.id, norm_value(shown))
                    truth[key] = f"{target.id} = {shown}"
    return truth


def cut(chunks: list, limit: int) -> list[str]:
    parts, current, size = [], [], 0
    for chunk in chunks:
        text = f"{chunk.header}\n{chunk.text}"
        cost = estimate_tokens(text) + 2
        if current and size + cost > limit:
            parts.append(current)
            current, size = [], 0
        current.append(text)
        size += cost
    if current:
        parts.append(current)
    return ["\n\n".join(part) for part in parts]


def prompt_for(body_parts: list[str]) -> str:
    numbered = [f"[part {i}]\n{text}" for i, text in enumerate(body_parts)]
    return "\n\n".join([INSTRUCTION, *numbered, CLOSING])


def score(items: list[dict], truth: dict) -> dict:
    names: dict[str, set[str]] = {}
    for name, value in truth:
        names.setdefault(name, set()).add(value)
    found, seen = set(), set()
    wrong = extra = 0
    for item in items:
        key = (str(item.get("name", "")).strip(), norm_value(item.get("value", "")))
        if key in seen:
            continue
        seen.add(key)
        if key in truth:
            found.add(key)
        elif key[0] in names:
            wrong += 1
        else:
            extra += 1
    return {
        "found": len(found),
        "truth": len(truth),
        "recall": round(len(found) / len(truth), 3),
        "precision": round(len(found) / len(seen), 3) if seen else 0.0,
        "wrong_value": wrong,
        "extra_name": extra,
        "returned": len(seen),
    }


def with_timeout(provider):
    return dataclasses.replace(provider, timeout=(10.0, 300.0))


def mistral(name: str, model: str, context: int) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        name=name,
        tier=0,
        url=R.MISTRAL_URL,
        model=model,
        api_key_env="MISTRAL_API_KEY",
        quota_pool=f"MISTRAL_API_KEY:{model}",
        context_window=context,
        max_output_tokens=32_768,
        timeout=(10.0, 300.0),
    )


def google_on(provider, key_env: str):
    return dataclasses.replace(
        provider,
        api_key_env=key_env,
        quota_pool=f"{key_env}:{provider.model}",
        timeout=(10.0, 300.0),
    )


ALL_SIZES = ["ALL", "28K", "12K"]
# name -> (providers, workers, sizes). Several providers are ROOMS: one per
# (key, model), each with its own minute allowance.
ENTRIES = {
    "flash-lite-3.5": ([with_timeout(R.GEMINI_3_5_FLASH_LITE)], 8, ALL_SIZES),
    "gemini-3.6-flash": (
        [google_on(R.GEMINI_3_6_FLASH, "GOOGLE_API_KEY_3")],
        1,
        ALL_SIZES,
    ),
    "glm-5.3-flash(cline)": ([with_timeout(R.CLINE_GLM_5_3_FLASH)], 2, ALL_SIZES),
    "deepseek-v4.1-flash(lite)": (
        [with_timeout(R.LITEROUTER_DEEPSEEK_V4_1_FLASH)],
        1,
        ALL_SIZES,
    ),
    "deepseek-v4-flash(orca)": (
        [with_timeout(R.ORCAROUTER_DEEPSEEK_V4_FLASH)],
        2,
        ALL_SIZES,
    ),
    "codestral-2508": ([mistral("Codestral", "codestral-2508", 256_000)], 3, ALL_SIZES),
    "ministral-14b": (
        [mistral("Ministral 14B", "ministral-14b-2512", 262_144)],
        2,
        ALL_SIZES,
    ),
    "ministral-8b": (
        [mistral("Ministral 8B", "ministral-8b-2512", 262_144)],
        3,
        ALL_SIZES,
    ),
    "ministral-3b": (
        [mistral("Ministral 3B", "ministral-3b-2512", 131_072)],
        3,
        ALL_SIZES,
    ),
    "open-mistral-nemo": (
        [mistral("Mistral Nemo", "open-mistral-nemo", 128_000)],
        3,
        ALL_SIZES,
    ),
    "gemma-26b": (
        [google_on(R.GEMMA_4_26B, key) for key in R.GOOGLE_KEYS],
        len(R.GOOGLE_KEYS),
        ["12K"],
    ),
    "gemma-31b": (
        [google_on(R.GEMMA_4_31B, key) for key in R.GOOGLE_KEYS],
        len(R.GOOGLE_KEYS),
        ["12K"],
    ),
}


class Rooms:
    """Gemma: about 16K input tokens a minute for each (key, model) room.

    A call that FAILS still uses up its room (measured 2026-10-22), so every
    attempt is counted, not only the ones that succeed.
    """

    LIMIT = 14_400
    WINDOW = 62.0

    def __init__(self, providers: list):
        self.providers = providers
        self.used: list[list[tuple[float, int]]] = [[] for _ in providers]
        self.lock = threading.Lock()

    def reserve(self, tokens: int):
        with self.lock:
            now = time.monotonic()
            best = None
            for index, log in enumerate(self.used):
                log[:] = [(t, n) for t, n in log if t > now - self.WINDOW]
                total = sum(n for _, n in log)
                wait = 0.0
                if total + tokens > self.LIMIT:
                    need, running = total + tokens - self.LIMIT, 0
                    for stamp, count in sorted(log):
                        running += count
                        if running >= need:
                            wait = max(0.0, stamp + self.WINDOW - now)
                            break
                if best is None or wait < best[0]:
                    best = (wait, index)
            wait, index = best
            self.used[index].append((now + wait, tokens))
            return self.providers[index], wait


def call_once(provider, prompt: str, rooms: Rooms | None, tokens: int):
    last = ""
    for _ in range(4):
        wait = 0.0
        if rooms is not None:
            provider, wait = rooms.reserve(tokens)
        if wait:
            time.sleep(wait)
        started = time.monotonic()
        try:
            result = provider.complete(
                prompt,
                max_tokens=min(MAX_OUT, provider.max_output_tokens),
                tool=TOOL,
            )
        except LLMError as exc:
            last = f"{exc.status}: {str(exc)[:160]}"
            if exc.status == 429:
                time.sleep(min(exc.retry_after or 25, 70))
            elif exc.status in (400, 401, 404, 413):
                break
            else:
                time.sleep(9)
            continue
        except ValueError as exc:
            last = f"refused locally: {exc}"
            break
        arguments = result.arguments
        if arguments is None or not isinstance(arguments.get("settings"), list):
            last = f"no usable arguments ({result.finish_reason})"
            continue
        return arguments["settings"], None, time.monotonic() - started
    return None, last, 0.0


def run_config(
    entry: str, size_name: str, chunks: list, truth: dict, out: pathlib.Path
):
    providers, workers, _ = ENTRIES[entry]
    parts = cut(chunks, SIZES[size_name])
    started = time.monotonic()
    results: list = [None] * len(parts)
    errors: list[str] = []
    rooms = Rooms(providers) if len(providers) > 1 else None

    def job(index: int):
        body = prompt_for([parts[index]])
        tokens = int(estimate_tokens(body) * 0.88)
        items, error, _took = call_once(providers[0], body, rooms, tokens)
        return index, items, error

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, items, error in pool.map(job, range(len(parts))):
            if items is None:
                errors.append(f"part {index}: {error}")
            else:
                results[index] = items
    merged = [item for part in results if part for item in part]
    (out / "raw" / f"{entry}__{size_name}.json").write_text(json.dumps(merged))
    return {
        "entry": entry,
        "size": size_name,
        "parts": len(parts),
        "failed_parts": len(errors),
        "seconds": round(time.monotonic() - started, 1),
        "errors": errors[:3],
        **score(merged, truth),
    }


def main(out: pathlib.Path, mode: str, only: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "raw").mkdir(exist_ok=True)
    files, chunks = load_corpus()
    truth = true_constants(files)
    used = sum(estimate_tokens(f"{c.header}\n{c.text}") for c in chunks)
    print(f"corpus: {len(files)} files, {len(chunks)} chunks, ~{used} est tokens")
    print(f"truth: {len(truth)} constants")
    if mode == "stats":
        for name, limit in SIZES.items():
            sizes = [estimate_tokens(p) for p in cut(chunks, limit)]
            print(name, "->", len(sizes), "parts:", sizes[:10])
        return

    log = out / "results.jsonl"
    done = set()
    if log.exists():
        for line in log.read_text().splitlines():
            row = json.loads(line)
            done.add((row["entry"], row["size"]))
    work = [
        (entry, size)
        for entry, (_, _, sizes) in ENTRIES.items()
        for size in sizes
        if (not only or entry in only) and (entry, size) not in done
    ]
    print(f"{len(work)} configurations to run", flush=True)

    def one(entry_size: tuple[str, str]) -> None:
        entry, size = entry_size
        try:
            row = run_config(entry, size, chunks, truth, out)
        except Exception as exc:  # keep the whole run alive
            row = {"entry": entry, "size": size, "crash": f"{exc!r}"[:200]}
        with open(log, "a") as handle:
            handle.write(json.dumps(row) + "\n")
        print(json.dumps(row), flush=True)

    # one thread per ENTRY: each entry runs its sizes one after the other
    by_entry: dict[str, list] = {}
    for item in work:
        by_entry.setdefault(item[0], []).append(item)
    with ThreadPoolExecutor(max_workers=6) as top:
        list(top.map(lambda items: [one(i) for i in items], by_entry.values()))
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[2] not in ("stats", "run"):
        sys.exit(__doc__)
    main(pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3:])
