from labpilot.embed.defaults import MAX_BATCH_SIZE, TIGHTEST_TOKENS_PER_MINUTE
from labpilot.ingest.defaults import MAX_CHUNK_TOKENS


def test_a_full_batch_of_capped_chunks_fits_the_tightest_token_budget():
    assert MAX_BATCH_SIZE * MAX_CHUNK_TOKENS <= TIGHTEST_TOKENS_PER_MINUTE
