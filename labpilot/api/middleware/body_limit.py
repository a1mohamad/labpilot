from __future__ import annotations

import json
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")

        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = self._content_length(scope)
        if declared is not None and declared > self.max_body_bytes:
            await self._refuse(scope, send)
            return

        # Content-Length can be absent on a streamed request, so buffer only up
        # to the limit and replay what was read for the application.
        buffered: list[Message] = []
        seen = 0

        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] != "http.request":
                break

            seen += len(message.get("body", b""))
            if seen > self.max_body_bytes:
                await self._refuse(scope, send)
                return

            if not message.get("more_body", False):
                break

        async def replay() -> Message:
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    # The streamed count stays authoritative when the declared
                    # value cannot be parsed.
                    return None
        return None

    async def _refuse(self, scope: Scope, send: Send) -> None:
        request_id = scope.get("state", {}).get("request_id") or str(uuid4())
        body = json.dumps(
            {
                "error": {
                    "code": "request_too_large",
                    "message": (
                        f"the request body is larger than {self.max_body_bytes} bytes"
                    ),
                    "request_id": request_id,
                    "attempts": [],
                }
            }
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"x-request-id", request_id.encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
