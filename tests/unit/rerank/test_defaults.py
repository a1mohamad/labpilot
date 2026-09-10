from labpilot.ingest.defaults import MAX_CHUNK_TOKENS
from labpilot.rerank.defaults import MAX_DOCUMENT_TOKENS, MAX_DOCUMENTS
from labpilot.store.defaults import SEARCH_LIMIT


def test_the_rerank_document_cap_agrees_with_the_chunk_cap():
    """Two packages, two reasons, one number - and they must not drift.

    ingest asks "what fits an embedder"; rerank asks "what Cohere treats as a
    single billed document". rerank/ is an adapter and may not import ingest/,
    so the agreement cannot be expressed as one constant. It is expressed here
    instead, because if the chunk cap ever rose above the rerank cap every
    single chunk would be split and billed twice, silently.
    """
    assert MAX_DOCUMENT_TOKENS >= MAX_CHUNK_TOKENS


def test_everything_we_retrieve_fits_one_rerank_call():
    """SEARCH_LIMIT chunks come back from the store and all of them are sent.

    If retrieval ever returned more than a reranker accepts, _check_inputs
    would refuse every call locally - loud, free, and completely useless. The
    mistake belongs in the build, not at runtime.
    """
    assert SEARCH_LIMIT <= MAX_DOCUMENTS
