import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from starlette.websockets import WebSocket

from nivaro_support import socket as support
from nivaro_support.contracts import Actor
from nivaro_support.live import NotificationBus


async def test_stalled_asgi_send_closes_socket_for_resynchronization(monkeypatch):
    origin = "http://localhost:8080"
    request = {
        "schema_version": 1,
        "type": "sync.request",
        "request_id": str(uuid4()),
        "conversation_id": str(uuid4()),
        "payload": {"after": 0},
    }
    monkeypatch.setattr(
        support, "handle_frame", AsyncMock(return_value=support.failure(request, "test"))
    )
    state = SimpleNamespace(
        allowed_origins={origin},
        authorization=SimpleNamespace(
            check_session=AsyncMock(
                return_value=Actor(
                    user_id=uuid4(),
                    kind="customer",
                    can_manage=False,
                )
            )
        ),
        database=None,
        notifications=NotificationBus(),
        activity_redis=None,
    )
    incoming = iter(
        [
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": json.dumps(request)},
        ]
    )
    outbound = []
    stalled = asyncio.Event()

    async def receive():
        return next(incoming)

    async def send(event):
        if event["type"] == "websocket.send":
            stalled.set()
            await asyncio.Future()
        else:
            outbound.append(event)

    await asyncio.wait_for(
        support.support_socket(
            WebSocket(
                {
                    "type": "websocket",
                    "headers": [(b"origin", origin.encode())],
                    "app": SimpleNamespace(state=state),
                },
                receive,
                send,
            )
        ),
        timeout=8,
    )
    assert stalled.is_set()
    assert outbound[-1]["type"] == "websocket.close" and outbound[-1]["code"] == 1013
