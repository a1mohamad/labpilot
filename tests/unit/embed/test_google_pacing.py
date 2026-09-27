"""THE GOOGLE BATCH PROBLEM, end to end, against a simulated Google.

Measured 2026-09-24 on gemini-embedding-001: 96 texts in one call -> 429;
40 texts -> 200; 40 more straight after -> 429. So Google refuses both a batch
that is too big AND a minute that is too full. The simulator enforces exactly
that - 30,000 tokens and 100 texts in any 60 seconds - on a fake clock, and the
REAL GoogleEmbedder with its SHIPPED settings goes through it. No network, no
quota, no waiting.

The limits below are LITERALS on purpose, not the constants under test: a test
that read GOOGLE_TOKENS_PER_MINUTE would move with it and could never fail.
"""

from __future__ import annotations

import json
import math
from collections import deque
from itertools import cycle

import pytest
import responses

from labpilot.embed import embed_batches, pacing
from labpilot.embed.errors import EmbeddingError
from labpilot.embed.google import GoogleEmbedder
from labpilot.tokens import estimate_tokens

GOOGLE_TOKENS_A_MINUTE = 30_000
GOOGLE_TEXTS_A_MINUTE = 100

BASE = "https://provider.test/v1beta/models"
URL = f"{BASE}/sim-embed:batchEmbedContents"
EMBEDDER = GoogleEmbedder(
    name="Simulated Gemini",
    url=BASE,
    model="sim-embed",
    dim=3,
    measured_tokens_per_minute=29_000,
)

# realistic chunks: the measured mean of 341 tokens, the 510 cap, and a small one
CORPUS = [
    "word " * (chars // 5) for chars, _ in zip(cycle([1_023, 1_530, 600]), range(250))
]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class SimulatedGoogle:
    """Refuses any request that would put the last 60 seconds over the limit.

    `ratio` scales how Google counts tokens against our chars/3 estimate, so a
    test can model an estimator that under-counts.
    """

    def __init__(self, clock: Clock, ratio: float = 1.0) -> None:
        self.clock, self.ratio = clock, ratio
        self.window: deque[tuple[float, int, int]] = deque()
        self.accepted = self.refused = 0

    def __call__(self, request):
        texts = [
            item["content"]["parts"][0]["text"]
            for item in json.loads(request.body)["requests"]
        ]
        tokens = sum(math.ceil(estimate_tokens(t) * self.ratio) for t in texts)
        now = self.clock()
        while self.window and now - self.window[0][0] >= 60:
            self.window.popleft()

        spent = sum(entry[1] for entry in self.window)
        sent = sum(entry[2] for entry in self.window)
        if (
            spent + tokens > GOOGLE_TOKENS_A_MINUTE
            or sent + len(texts) > GOOGLE_TEXTS_A_MINUTE
        ):
            self.refused += 1
            return 429, {}, json.dumps({"error": {"status": "RESOURCE_EXHAUSTED"}})

        self.window.append((now, tokens, len(texts)))
        self.accepted += 1
        body = {"embeddings": [{"values": [1.0, 0.0, 0.0]} for _ in texts]}
        return 200, {}, json.dumps(body)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    pacing.forget()
    yield
    pacing.forget()


def run(clock, google, texts):
    responses.add_callback(responses.POST, URL, callback=google)
    return [
        v
        for batch in embed_batches(EMBEDDER, texts, clock=clock, sleep=clock.sleep)
        for v in batch.vectors
    ]


@responses.activate
def test_the_simulator_refuses_what_we_used_to_send():
    # the premise: two full batches inside one minute. If this passed, the
    # simulator could not tell a fixed embed_batches from a broken one
    clock = Clock()
    google = SimulatedGoogle(clock)
    responses.add_callback(responses.POST, URL, callback=google)

    EMBEDDER.embed(["word " * 306] * 40)  # ~20,400 tokens, the capped batch
    with pytest.raises(EmbeddingError) as caught:
        EMBEDDER.embed(["word " * 306] * 40)
    assert caught.value.status == 429


@responses.activate
def test_a_whole_corpus_goes_through_without_one_refusal():
    clock = Clock()
    google = SimulatedGoogle(clock)

    assert len(run(clock, google, CORPUS)) == len(CORPUS)
    assert google.refused == 0


@responses.activate
def test_two_ingests_in_a_row_share_one_minute():
    # side A then side B: two separate calls on the SAME Google bucket. A
    # window that forgot A would send B's first batch into a full minute
    clock = Clock()
    google = SimulatedGoogle(clock)

    side_a = run(clock, google, CORPUS[:76])
    # premise: A ended on a FULL minute, with no wait that emptied it
    assert google.accepted == 2 and clock.now == 0
    run(clock, google, CORPUS[76:152])
    assert google.refused == 0
    assert len(side_a) == 76


@responses.activate
def test_an_estimate_that_under_counts_still_finishes():
    # if Google counts 25% more tokens than chars/3, the pace alone will be
    # refused sometimes - and the wait must carry the ingest through anyway
    clock = Clock()
    google = SimulatedGoogle(clock, ratio=1.25)

    assert len(run(clock, google, CORPUS)) == len(CORPUS)
    assert google.refused > 0, "premise: the under-count must really bite"


# Short texts hit Google's 100 TEXTS a minute long before its tokens - the
# case where counting HTTP calls instead of texts under-promised by 40x.
SHORT = ["short text"] * 900


@pytest.mark.parametrize("corpus", [CORPUS, SHORT], ids=["realistic", "short-texts"])
@responses.activate
def test_the_time_the_user_is_shown_is_the_time_it_takes(corpus):
    clock = Clock()
    google = SimulatedGoogle(clock)
    run(clock, google, corpus)

    tokens = sum(estimate_tokens(t) for t in corpus)
    promised = EMBEDDER.embedding_minutes(tokens=tokens, chunks=len(corpus))
    taken = clock.now / 60
    assert google.refused == 0
    assert 0.8 * promised <= taken <= 1.3 * promised, (promised, taken)
