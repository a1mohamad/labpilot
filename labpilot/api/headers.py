"""The header that carries the id of one request, as text and as raw bytes."""

REQUEST_ID_HEADER = "X-Request-ID"
# ASGI carries header names as lower-case bytes.
RAW_REQUEST_ID_HEADER = REQUEST_ID_HEADER.lower().encode("ascii")
