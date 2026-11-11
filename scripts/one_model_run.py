"""Our real agent, search path forced, ONE model for every chain kind, no fallback.

Every LLMClient.generate() of the product is rerouted to a client whose chain is
exactly one tier, with no retry. By default a call gets the FIRST live tier of
its own chain (the model the product means to use). The config replaces a model
that turned out not to work:

    "overrides": {"<first tier of the chain>": "<model to use instead>",
                  "<step>|<first tier of the chain>": "<model, for ONE step>"}
    "stop_on_fail": true      end the run quickly at the first failed call

A failed call is recorded (step, tool, model, error) and printed, and the run
goes on, so the slow nodes after it still get timed. A model is replaced when a
whole node fails with it, not for one malformed answer.

The files are ingested once into the schema labpilot_onemodel and kept. Drop it
by hand when you are done:  drop schema labpilot_onemodel cascade

    python -m scripts.one_model_run PREFIX '{"overrides": {...}}'
"""

import json
import sys
import threading
import time
import traceback
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, ".")

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")

import labpilot.llm.chain as chain  # noqa: E402
import scripts.time_one_question as tq  # noqa: E402
from labpilot.api import asking  # noqa: E402
from labpilot.api.checkpoints import open_saver  # noqa: E402
from labpilot.api.ingestion import ingest_artifact, ingest_source  # noqa: E402
from labpilot.llm import (  # noqa: E402
    CHAIN,
    KNOWN_DEAD,
    AllFreeTiersExhausted,
    LLMClient,
)
from labpilot.sources import open_folder  # noqa: E402
from labpilot.store import connect, create_schema, database_url  # noqa: E402
from labpilot.timing import collecting, current_step  # noqa: E402

prefix = sys.argv[1]
config = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
OVERRIDES = config.get("overrides", {})
SCHEMA = "labpilot_onemodel"
OFFSET = time.time() - time.perf_counter()
ROOT = Path(__file__).resolve().parents[1]

lock = threading.Lock()
http: list[dict] = []
calls: list[dict] = []
prompts: list[dict] = []
failures: list[dict] = []
stopped = threading.Event()

# ---- the independent clock ---------------------------------------------------
_real_request = requests.sessions.Session.request


def timed_request(self, method, url, *args, **kwargs):
    started = time.perf_counter()
    status = None
    try:
        response = _real_request(self, method, url, *args, **kwargs)
        status = response.status_code
        return response
    except BaseException as exc:
        status = type(exc).__name__
        raise
    finally:
        with lock:
            http.append(
                {
                    "thread": threading.get_ident(),
                    "start": started + OFFSET,
                    "end": time.perf_counter() + OFFSET,
                    "host": url.split("/")[2] if "//" in url else url,
                    "status": status,
                }
            )


requests.sessions.Session.request = timed_request

_real_log_call = chain.log_call


def seen_log_call(**kwargs):
    with lock:
        calls.append(
            {
                "thread": threading.get_ident(),
                "end": time.perf_counter() + OFFSET,
                **kwargs,
            }
        )
    _real_log_call(**kwargs)


chain.log_call = seen_log_call

# ---- the routing: one tier for every call ------------------------------------
alive = [p for p in CHAIN if p.name not in KNOWN_DEAD]
_round = {}


def pick(client, step=""):
    first = client.chain[0].name
    # "step|first tier" replaces a model for ONE step only; "first tier" for all.
    wanted = OVERRIDES.get(f"{step}|{first}", OVERRIDES.get(first, first))
    base = wanted.split(" (key ")[0]
    options = [p for p in alive if p.name == base or p.name.startswith(base + " (key ")]
    if not options:
        raise SystemExit(f"no live tier called {base!r}")
    i = _round.get(base, 0)
    _round[base] = i + 1
    return first, options[i % len(options)]


_real_generate = LLMClient.generate


def one_model_generate(self, prompt, **kwargs):
    step = current_step.get()
    tool = kwargs.get("tool")
    with lock:
        prompts.append(
            {
                "step": step,
                "tool": None
                if tool is None
                else {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
                "max_tokens": kwargs.get("max_tokens"),
                "prompt": prompt,
                "chain_first": self.chain[0].name if self.chain else None,
            }
        )
    if stopped.is_set():
        raise AllFreeTiersExhausted(())
    first, provider = pick(self, step)
    read = 600.0 if step == "respond" else 300.0
    single = LLMClient(
        chain=(replace(provider, timeout=(10.0, read)),),
        max_retries_per_tier=0,
        total_budget=1200.0,
        max_rejected_answers=1,
    )
    try:
        return _real_generate(single, prompt, **kwargs)
    except AllFreeTiersExhausted as exc:
        row = {
            "step": step,
            "tool": tool.name if tool else "",
            "chain_first": first,
            "model": provider.name,
            "error": "; ".join(a.error for a in exc.attempts)[:300],
            "at": time.time(),
        }
        with lock:
            failures.append(row)
        print("FAILED", json.dumps(row), flush=True)
        if config.get("stop_on_fail"):
            stopped.set()
        raise


LLMClient.generate = one_model_generate

# ---- the worst case: never stuff ----------------------------------------------
asking.fits_whole = lambda *a, **k: False

# ---- the run ------------------------------------------------------------------
base = database_url()
with connect(base, autocommit=True) as admin:
    exists = admin.execute(
        "select 1 from pg_namespace where nspname = %s", (SCHEMA,)
    ).fetchone()
    if not exists:
        admin.execute(f"create schema {SCHEMA}")
        print("schema created, files will be ingested", flush=True)

with connect(tq.with_search_path(base, SCHEMA), autocommit=True) as conn:
    create_schema(conn)
    open_saver(conn).setup()
    ids = {
        row[0][0]: row[0] for row in conn.execute("select id from artifacts").fetchall()
    }
    if "A" not in ids or "B" not in ids:
        pair = tq.PAIRS["otp"]
        a_path = ROOT / pair["a"]
        ids["A"] = ingest_artifact(
            conn, a_path.read_bytes(), name=a_path.name, side="A"
        ).artifact.id
        with open_folder(ROOT / pair["b"]) as source:
            ids["B"] = ingest_source(conn, source, side="B").artifact.id
        print("ingested", ids, flush=True)
    conn.execute("delete from saved_results")

    thread = f"onemodel-{int(time.time())}"
    began = time.perf_counter()
    result = None
    with collecting() as mine:
        try:
            result = tq.ask_once(conn, ids["A"], ids["B"], thread, tq.FIRST, "first")
        except Exception:  # noqa: BLE001 - reported below
            traceback.print_exc()
    finished = time.perf_counter()
    json.dump(
        {
            "http": http,
            "calls": calls,
            "failures": failures,
            "records": mine.records,
            "outside_start": began + OFFSET,
            "outside_end": finished + OFFSET,
            "outside_seconds": finished - began,
            "overrides": OVERRIDES,
            "ok": result is not None and not failures,
        },
        open(f"{prefix}_raw.json", "w"),
        indent=1,
    )
    json.dump(prompts, open(f"{prefix}_prompts.json", "w"))
    print(
        "OK"
        if result is not None and not failures
        else f"FAILED: {len(failures)} calls",
        flush=True,
    )
