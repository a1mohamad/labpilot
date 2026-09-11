from __future__ import annotations

DEFAULT_TIMEOUT: tuple[float, float] = (10.0, 60.0)

# Cohere bills ONE search unit per call for up to 100 documents, so 50 and 100
# cost it exactly the same. Voyage and Cloudflare bill by token, where 100
# documents cost twice as much as 50. The cap here is therefore the widest any
# provider accepts for one unit of billing; which number we actually SEND is a
# per-provider question that slice 8 must measure, because on Cohere half of
# every paid call is currently wasted.
MAX_DOCUMENTS = 100

# Cohere splits any document longer than this into pieces and bills each one,
# which silently multiplies the document count every rerank budget in
# CLAUDE.md assumes. The chunk cap fix of 2026-09-05 put 0 of 4,889 chunks
# over the line, so this guard should never fire on our own chunks - and a
# guard that never fires is exactly the one worth keeping, because the failure
# it prevents is a bill, not an exception.
#
# The number equals ingest's MAX_CHUNK_TOKENS and is DERIVED INDEPENDENTLY:
# rerank/ is an adapter and may not import ingest/, and the two numbers answer
# different questions - ingest asks "what fits an embedder", this asks "what
# Cohere treats as one document". test_rerank_agrees_with_the_chunk_cap pins
# that they cannot drift apart.
MAX_DOCUMENT_TOKENS = 510

# How many documents survive reranking into the prompt. 50 chunks at ~229
# tokens is ~11,450, which FITS the evidence budget - so the cut is about
# quality, not capacity: a wide window dilutes the signal and invites "lost in
# the middle", a narrow one risks dropping the answer. MEASURED in slice 6.
RERANK_TOP_N = 10

# Output budget for a listwise ranking. 50 two-digit numbers and commas is
# ~200 tokens; the rest is headroom for a model that reasons in prose before
# answering, which gemma does and flash-lite does not.
RERANK_MAX_TOKENS = 4_096
