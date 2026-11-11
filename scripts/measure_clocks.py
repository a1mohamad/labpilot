"""Run scripts/time_one_question.py with a SECOND, independent clock beside it.

The timer under test uses time.monotonic()/time.time() inside the nodes. This
harness adds, without changing the timer:

  * an outside stopwatch around every ask(), with time.perf_counter()
  * a clock around every HTTP request (requests.Session.request), with
    perf_counter, recording the thread that made it
  * its own copy of the timer's records (a second collector)
  * the thread of every generate() call (a wrapper that calls the real log_call)
  * every prompt, tool and max_tokens of every generate() call

Everything goes to a raw JSON file that scripts/verify_clocks.py reads.

    python -m scripts.measure_clocks PAIR RUNS_FIRST OUT_PREFIX [FOLLOW_UPS]
"""

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, ".")

import requests  # noqa: E402

import labpilot.llm.chain as chain  # noqa: E402
import scripts.time_one_question as tq  # noqa: E402
from labpilot.llm import LLMClient  # noqa: E402
from labpilot.timing import collecting, current_step  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FOLLOW = sys.argv[4] if len(sys.argv) > 4 else "saved,chat"
pair, runs_first, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
OFFSET = time.time() - time.perf_counter()  # perf_counter -> wall clock

http: list[dict] = []
calls: list[dict] = []
asks: list[dict] = []
prompts: list[dict] = []
lock = threading.Lock()

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

_real_generate = LLMClient.generate


def seen_generate(self, prompt, **kwargs):
    tool = kwargs.get("tool")
    with lock:
        prompts.append(
            {
                "step": current_step.get(),
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
                "chain_len": len(self.chain),
                "retries": self.max_retries_per_tier,
                "budget": self.total_budget,
            }
        )
    return _real_generate(self, prompt, **kwargs)


LLMClient.generate = seen_generate

_real_ask_once = tq.ask_once


def watched_ask_once(conn, a, b, thread, question, kind):
    h0, c0 = len(http), len(calls)
    with collecting() as mine:
        began = time.perf_counter()
        run = _real_ask_once(conn, a, b, thread, question, kind)
        finished = time.perf_counter()
    with lock:
        asks.append(
            {
                "kind": kind,
                "outside_start": began + OFFSET,
                "outside_end": finished + OFFSET,
                "outside_seconds": finished - began,
                "timer_wall": run["wall"],
                "http": [h0, len(http)],
                "calls": [c0, len(calls)],
                "records": mine.records,
            }
        )
        json.dump(
            {"http": http, "calls": calls, "asks": asks},
            open(f"{prefix}_raw.json", "w"),
            indent=1,
        )
        json.dump(prompts, open(f"{prefix}_prompts.json", "w"))
    return run


tq.ask_once = watched_ask_once
sys.argv = [
    "time_one_question",
    "--pair",
    pair,
    "--runs-first",
    runs_first,
    "--out",
    f"{prefix}_timer.json",
    "--follow-ups",
    FOLLOW,
    "--root",
    str(ROOT),
]
tq.main()
