from __future__ import annotations

DEFAULT_TIMEOUT: tuple[float, float] = (10.0, 60.0)
MAX_BATCH_SIZE = 96
# codestral-embed is the tighter of the two: 50,000 tokens/minute, against
# mistral-embed's 20,000,000. MAX_BATCH_SIZE is derived from this number.
TIGHTEST_TOKENS_PER_MINUTE = 50_000
