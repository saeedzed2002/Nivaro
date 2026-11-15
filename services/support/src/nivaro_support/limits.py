import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BoundedBody:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        data = bytearray()
        status, code = 0, ""
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(data) + len(chunk) > 16384:
                        status, code = 413, "request.too_large"
                        break
                    data.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            status, code = 408, "request.timeout"
        if status:
            await JSONResponse(
                status_code=status,
                content={"error": {"code": code, "request_id": scope["state"]["request_id"]}},
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(data), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
