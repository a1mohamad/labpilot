from __future__ import annotations

# Measured 2026-09-03 on the session pooler: statement_timeout is 2min and
# idle_in_transaction_session_timeout is 0 (no limit). So one transaction may
# stay open across embedder calls, which is what lets ingest stream.
CONNECT_TIMEOUT = 15
# Rows held in memory at once while writing: 96 x 1536 floats x 32 bytes is
# about 4.7MB, against the 512MB the API and ingest share. The number comes
# from that budget, NOT from the embedder's MAX_BATCH_SIZE -- store/ may not
# import embed/, and the two limits answer different questions.
INSERT_BATCH_SIZE = 96
# Retrieve wide, then rerank to ~10. Reranking fixes the ORDER of what came
# back; it can never recover a chunk the search did not return, so the wide
# number belongs here and not at the rerank step.
SEARCH_LIMIT = 50
