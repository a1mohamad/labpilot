from __future__ import annotations

# Measured 2026-09-03 on the session pooler: statement_timeout is 2min and
# idle_in_transaction_session_timeout is 0 (no limit). So one transaction may
# stay open across embedder calls, which is what lets ingest stream.
CONNECT_TIMEOUT = 15
