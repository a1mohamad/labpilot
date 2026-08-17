from __future__ import annotations

from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = b"x-request-id"


class RequestIDMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            # Headers can only be changed before the response body starts.
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(name.lower() == REQUEST_ID_HEADER for name, _ in headers):
                    headers.append((REQUEST_ID_HEADER, request_id.encode("ascii")))
                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, send_with_request_id)
