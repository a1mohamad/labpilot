"""Draft a query fixture for a corpus, from the corpus itself.

    PYTHONPATH=. python scripts/draft_queries.py cobra
    PYTHONPATH=. python scripts/draft_queries.py cobra --n=20 --model=gemma31

Twelve corpora need about 170 queries between them, each one carrying ground
truth. Writing them all by hand is the honest method and it does not fit in a
day, so they are DRAFTED by a cheap model against the real chunk text and then
VALIDATED mechanically. The bias that buys is written down rather than hidden -
see "what this method is worth" at the bottom.

THE ONE RULE THAT MATTERS, and it is easy to break by accident:

    A query is NEVER filtered on whether retrieval finds it.

Dropping the queries our embedder misses would build a fixture that agrees
with our embedder, and every later number would be measuring the filter. The
validator checks that a query is well FORMED - resolvable, specific, no leaked
identifier - and never that it is well ANSWERED.

Ground truth comes from deterministic quoting, the same mechanism the citation
layer already uses: the drafter must copy one exact line out of the chunk it
was given, and that line is located in the file to produce `expects`. A line
number found this way survives re-chunking, which a chunk index would not.
"""

from __future__ import annotations

import dataclasses
import json
import random
import re
import sys
import time

from dotenv import load_dotenv

from labpilot.llm import AllFreeTiersExhausted, LLMClient
from labpilot.llm.registry import GEMINI_3_5_FLASH_LITE, GEMMA_4_26B, GEMMA_4_31B
from labpilot.tokens import estimate_tokens
from scripts import corpora

MODELS = {
    "gemma31": GEMMA_4_31B,
    "gemma26": GEMMA_4_26B,
    "flashlite": GEMINI_3_5_FLASH_LITE,
}

# The second Google account is a second QUOTA, not a spare key - Google bills
# per project per model - so four gemma entries is 57,600 calls a day.
SECOND_KEY = "GOOGLE_API_KEY_2"

# Five kinds, because the two older fixtures use exactly these and a new corpus
# that invented its own could not be compared with them. They are also the axis
# every routing finding in this project has been argued along.
KINDS = ("constant", "behaviour", "error", "api", "structure")

PER_CALL = 5
# A schema turns the reply from prose-wrapped-around-an-answer into an answer.
# Measured in slice 6: one gemma ranking went 45.5s -> 14.4s with one.
SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "n": {"type": "INTEGER"},
            "question": {"type": "STRING"},
            "asks": {"type": "STRING", "enum": list(KINDS)},
            "wording": {"type": "STRING", "enum": ["named", "paraphrase"]},
            "anchor": {"type": "STRING"},
        },
        "required": ["n", "question", "asks", "wording", "anchor"],
    },
}

INSTRUCTION = """You write evaluation questions for a code and document search system.

You are given {count} numbered extracts. For EACH extract write ONE question.

Rules, and rule 3 is the one that decides whether the question is usable:

1. The question must be answerable BY THAT EXTRACT. Someone reading only that
   extract can answer it; someone reading a different part of the project
   cannot.
2. Write it the way a developer would ask a colleague. One sentence, lower
   case, no question mark needed. Never mention "the extract", "this code",
   "the document" or a line number - the asker has not seen it.
3. NEVER use an identifier that appears in the extract: no function name, no
   type name, no constant name, no file name, no rare spelled-out token.
   Describe what the thing DOES instead. "how long does it wait before giving
   up" is right; "what is defaultTimeout set to" is wrong, because it would
   measure string matching rather than search.
4. `asks` is the kind of thing wanted:
   constant  - a specific configured value or limit
   behaviour - what happens when something runs
   error     - what happens when something goes wrong, or is refused
   api       - how a caller is meant to use it
   structure - how the thing is organised, or what a part is for
5. `wording`: "named" if you reused ordinary words that also appear in the
   extract, "paraphrase" if you deliberately avoided its words.
6. `anchor` must be ONE line copied EXACTLY from the extract - the line the
   answer really sits on. Copy it character for character, no ellipsis.

Answer with a JSON array of {count} objects, one per extract, using the `n`
you were given.

{extracts}"""


def sample(chunks: list, n: int, seed: int = 8) -> list[int]:
    """Pick `n` chunk positions, spread ACROSS FILES rather than at random.

    A uniform random sample of a repository is mostly its biggest file, so the
    fixture would measure one file's retrievability and call it a corpus. Here
    every file is visited in turn and gives up one chunk before any file gives
    a second, which also makes the sample reproducible from the seed alone.

    Boilerplate is skipped: a chunk that is mostly a licence header or a block
    of imports answers no question anybody would ask, and a drafter handed one
    invents a question about copyright.
    """
    rng = random.Random(seed)
    by_file: dict[str, list[int]] = {}
    for i, chunk in enumerate(chunks):
        if estimate_tokens(chunk.text) < 60:
            continue
        head = chunk.text[:400].lower()
        boilerplate = ("copyright", "licensed under", "all rights reserved")
        if any(word in head for word in boilerplate):
            continue
        if head.startswith(("import ", "package ", "#include", "use ")):
            continue
        by_file.setdefault(chunk.source, []).append(i)

    for positions in by_file.values():
        rng.shuffle(positions)

    picked: list[int] = []
    files = sorted(by_file)
    rng.shuffle(files)
    round_ = 0
    while len(picked) < n:
        added = False
        for source in files:
            if round_ < len(by_file[source]):
                picked.append(by_file[source][round_])
                added = True
                if len(picked) == n:
                    break
        if not added:
            break
        round_ += 1
    return picked


def extract(chunk, n: int) -> str:
    return f"--- extract {n} ({chunk.source})\n{chunk.text}\n"


def anchor_line(chunk, anchor: str) -> int | None:
    """Resolve the quoted line to a line NUMBER in the real file.

    Matched on WHITESPACE-NORMALISED text, so indentation the drafter dropped
    does not lose the anchor - the same tolerance citations.resolve already
    applies, for the same reason. A drafter that invented a line returns None
    and the query is dropped rather than given a plausible wrong number.

    Stripping alone was not enough, and PDF is why: extracted text carries the
    spacing of the PAGE, not of a sentence, so a faithfully copied line comes
    back with runs of spaces the model quietly collapses. Measured on the
    papers corpus - 23 of 36 drafts dropped on an anchor that was really
    there, against 1 of 36 on Rust.
    """
    wanted = " ".join(anchor.split())
    if not wanted:
        return None

    lines = chunk.text.splitlines()
    flat = [" ".join(line.split()) for line in lines]
    for offset, line in enumerate(flat):
        if line == wanted or (len(wanted) > 20 and wanted in line):
            return chunk.start_line + offset

    # Still nothing, so try ACROSS the line break. Extracted prose wraps
    # wherever the page wrapped, and a quoted sentence then spans two lines
    # that no per-line comparison can match. The line reported is where the
    # match STARTS, which is the line a citation would point at.
    if len(wanted) <= 20:
        return None
    joined, starts = "", []
    for line in flat:
        starts.append(len(joined))
        joined += line + " "
    found = joined.find(wanted)
    if found < 0:
        return None
    offset = max(i for i, start in enumerate(starts) if start <= found)
    return chunk.start_line + offset


def structured(model_key: str) -> tuple:
    """The chosen model on both accounts, each asked for JSON.

    thinking is already None on every gemma entry. The schema is what makes
    the reply parseable instead of prose with an answer inside it - measured
    in slice 6, where one gemma ranking went 45.5s to 14.4s with one.
    """
    config = {"responseMimeType": "application/json", "responseSchema": SCHEMA}
    first = dataclasses.replace(MODELS[model_key], generation_config=config)
    if model_key.startswith("gemma"):
        others = [MODELS[k] for k in ("gemma31", "gemma26") if k != model_key]
    else:
        others = []
    tiers = [first] + [dataclasses.replace(o, generation_config=config) for o in others]
    return tuple(
        t
        for tier in tiers
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


def clip(text: str) -> str:
    """The JSON array, and nothing the model wrote around it.

    A responseSchema is a strong hint and not a guarantee: gemma returns a
    valid array and then a stray ``` fence, which `json.loads` refuses with
    "Extra data". Cutting to the outermost brackets costs nothing and removes a
    whole class of retry that would otherwise look like a dead model.
    """
    start, end = text.find("["), text.rfind("]")
    return text[start : end + 1] if 0 <= start < end else text


def attempt(client: LLMClient, prompt: str, tries: int = 3) -> list | None:
    """Ask the gemma chain, and tolerate the failures this tier is known for.

    gemma answers HTTP 500 "Internal error encountered" for roughly one call in
    three, and 503 when Google is busy - measured in slice 6 on BOTH accounts,
    so it is Google's serving of the model and not a key. Hand-rolling the
    retry was tried first and kept losing whole batches.

    So this uses the project's OWN fallback loop instead, over four gemma
    buckets: 31B and 26B on two accounts, 14,400 calls a day each. The
    five-way rule already knows that 503 is worth retrying on the same tier
    and that a spent pool should be skipped, and reusing it means the drafting
    job cannot fail in a way the product would not also have handled.
    """
    for i in range(tries):
        try:
            return json.loads(clip(client.generate(prompt, max_tokens=4096).text))
        except (AllFreeTiersExhausted, json.JSONDecodeError) as exc:
            print(f"      retry {i + 1}/{tries}: {str(exc)[:70]}")
            time.sleep(3 + 5 * i)
    return None


def keep(query: dict, chunk) -> str | None:
    """Why this draft is unusable, or None if it is fine.

    The SAME rules the validator applies, so a fixture cannot pass the check
    that built it and fail the check that judges it. Applied here as well
    because a rejected draft can still be REPLACED at this point - after the
    fixture is written, a rejection is just a hole in it.

    Note what is NOT checked: whether retrieval finds the answer. Filtering on
    that would build a fixture that agrees with our own embedder.
    """
    if corpora.generic(query["query"]):
        return f"generic: {query['query']!r}"
    stolen = corpora.leaked(chunk.text, query["query"])
    if stolen:
        return f"leaked {sorted(stolen)}"
    return None


def balance(pool: list[dict], n: int) -> list[dict]:
    """Take `n` queries with the five kinds as even as the pool allows.

    The drafter chooses its own `asks`, and left alone it choose badly: the
    first cobra run came back 11 behaviour, 4 error, 3 structure, 2 constant
    and NOT ONE api. Every routing finding in this project is a per-category
    comparison, and a category with two queries in it cannot support one.

    Forcing a category per extract was the other option and is worse - a chunk
    with no constant in it would get a made-up question about a constant. So
    the drafter stays free, we over-draft, and the SELECTION does the
    balancing.
    """
    buckets: dict[str, list[dict]] = {}
    for query in pool:
        buckets.setdefault(query["asks"], []).append(query)

    taken: list[dict] = []
    while len(taken) < n and any(buckets.values()):
        for kind in KINDS:
            if buckets.get(kind):
                taken.append(buckets[kind].pop(0))
                if len(taken) == n:
                    break
    return taken


def draft(corpus: str, n: int, model_key: str) -> list[dict]:
    chunks = corpora.chunks_for(corpus)
    # Over-draft, because some drafts are rejected and the kinds come back
    # lopsided. Rejecting from a pool costs a few cheap calls; rejecting from
    # an exact-sized run leaves the fixture short and unbalanced.
    picked = sample(chunks, int(n * 1.8))
    print(
        f"{corpus}: {len(chunks)} chunks, sampled {len(picked)} across "
        f"{len({chunks[i].source for i in picked})} files"
    )

    client = LLMClient(chain=structured(model_key))
    out: list[dict] = []
    for start in range(0, len(picked), PER_CALL):
        batch = picked[start : start + PER_CALL]
        body = "\n".join(extract(chunks[i], j + 1) for j, i in enumerate(batch))
        prompt = INSTRUCTION.format(count=len(batch), extracts=body)
        drafted = attempt(client, prompt)
        if drafted is None:
            print(f"    batch {start}: no usable reply, skipped")
            continue

        for item in drafted:
            try:
                position = batch[int(item["n"]) - 1]
            except (KeyError, ValueError, IndexError):
                continue
            chunk = chunks[position]
            line = anchor_line(chunk, item.get("anchor", ""))
            if line is None:
                print(f"    dropped: anchor not in chunk ({chunk.source})")
                continue
            candidate = {
                "query": item["question"].strip().rstrip("?"),
                "asks": item["asks"],
                "wording": item["wording"],
                "file": chunk.source,
                "expects": [line],
                "anchor": item["anchor"].strip(),
            }
            why = keep(candidate, chunk)
            if why:
                print(f"    rejected: {why}")
                continue
            out.append(candidate)
        print(f"    pool {len(out)}/{len(picked)}", flush=True)
    return out


def interleave(queries: list[dict], prefix: str) -> list[dict]:
    """Order so that ANY PREFIX of the fixture is a stratified sample.

    The `requests` fixture is grouped by category, and slice 6 learned what
    that costs the hard way: a run stopped after 8 queries had measured one
    category and read like a corpus result. Round-robin over the kinds makes a
    truncated run honest by construction.
    """
    buckets: dict[str, list[dict]] = {kind: [] for kind in KINDS}
    for query in queries:
        buckets.setdefault(query["asks"], []).append(query)

    ordered: list[dict] = []
    while any(buckets.values()):
        for kind in KINDS:
            if buckets.get(kind):
                ordered.append(buckets[kind].pop(0))
    for i, query in enumerate(ordered, 1):
        query["id"] = f"{prefix}{i:02d}"
    return [{"id": q.pop("id"), **q} for q in ordered]


def main() -> int:
    load_dotenv(".env")
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <corpus> [--n=20] [--model=gemma31]")
        return 2

    corpus = sys.argv[1]
    n = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--n=")), 20)
    model = next(
        (a.split("=")[1] for a in sys.argv if a.startswith("--model=")), "gemma31"
    )

    _, folder = corpora._spec(corpus)
    fixture = json.loads((folder / "queries.json").read_text(encoding="utf-8"))

    pool = draft(corpus, n, model)
    drafted = balance(pool, n)
    print(f"pool {len(pool)} -> kept {len(drafted)}, balanced across kinds")
    prefix = re.sub(r"[^A-Z]", "", corpus.upper())[:2] or corpus[:2].upper()
    fixture["queries"] = interleave(drafted, prefix)
    fixture["corpus"]["drafted_by"] = MODELS[model].model
    (folder / "queries.json").write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(fixture['queries'])} queries to {folder}/queries.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
