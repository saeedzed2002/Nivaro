import asyncio
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BoundedBody:
    """Bound chunked bodies before JSON parsing; no Content-Length trust."""

    def __init__(self, app: ASGIApp, max_bytes: int = 65536) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] == "PUT"
            and scope["path"] in {"/api/v1/me/avatar", "/api/v1/admin/me/avatar"}
        ):
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        chunks = []
        size = 0
        failure = None
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > self.max_bytes:
                        failure = (413, "request.too_large", "Identity request exceeds body limit")
                        break
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            failure = (408, "request.timeout", "Identity request body timed out")
        if failure is not None:
            request_id = str(uuid4())
            response = JSONResponse(
                status_code=failure[0],
                content={
                    "error": {
                        "code": failure[1],
                        "message": failure[2],
                        "details": [],
                        "request_id": request_id,
                    }
                },
                headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
