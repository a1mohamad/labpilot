"""Paths and the network check that every routing script shares (section 33).

The routing scripts measure the models and propose new tables for
labpilot/llm/ratings.py and labpilot/llm/accuracy.py. They write only under
artifacts/routing-bench/ (git-ignored) unless a script is run with --apply.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

BENCH = REPO / "artifacts" / "routing-bench"
DATA = BENCH / "data"  # the labelled cases (collect_data.py builds it)
LOGS = BENCH / "logs"  # one JSON line per call or per bench item
PROPOSED = BENCH / "proposed"  # tables a script proposes, before --apply
LLM = REPO / "labpilot" / "llm"  # where --apply writes ratings.py and accuracy.py

for folder in (DATA, LOGS, PROPOSED):
    folder.mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")


def today() -> str:
    return time.strftime("%Y-%m-%d")


def append(path: Path, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def check_network(*, required: bool = True) -> bool:
    """CLAUDE.md's network precondition: say the exit ISP, then probe Google.

    The ISP is only a hint; the probe decides. A refused exit (400) looks exactly
    like a dead provider, so a run on a bad exit would record false failures.
    """
    import requests

    load_env()
    try:
        info = requests.get("https://ipinfo.io/json", timeout=15).json()
        print(f"exit: {info.get('ip')}  {info.get('org')}  {info.get('city')}")
    except requests.RequestException as exc:
        print(f"exit: unknown ({exc.__class__.__name__})")
    key = os.environ.get("GOOGLE_API_KEY", "")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.5-flash-lite:generateContent"
    )
    body = {
        "contents": [{"parts": [{"text": "say ok"}]}],
        "generationConfig": {"maxOutputTokens": 2048},
    }
    try:
        code = requests.post(
            url, json=body, headers={"x-goog-api-key": key}, timeout=60
        ).status_code
    except requests.RequestException:
        code = 0
    print(f"google probe: {code}")
    if code != 200 and required:
        print(
            "STOP: the Google probe is not 200. 400 = the exit is refused (change "
            "the VPN server), 403 = the account, 429 = quota. Use --no-network-check "
            "to run anyway."
        )
        sys.exit(2)
    return code == 200
