import asyncio
import json
from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import Response
from starlette.types import Message as ASGIMessage

from nivaro_support.activity import ActivitySession
from nivaro_support.authorization import IdentityAuthorization
from nivaro_support.contracts import Actor, Kind, SendMessage, SupportError
from nivaro_support.conversations import mark_read, send_message
from nivaro_support.live import ConversationStream, history
from nivaro_support.settings import Database
from nivaro_support.socket_contracts import (
    CLIENT,
    Acceptance,
    ActivityChanged,
    ActivityExpiry,
    ActivityFrame,
    ClientMessage,
    FailureCode,
    MarkRead,
    MessageAccepted,
    MessageCreated,
    MessageSend,
    ReadChanged,
    ServerMessage,
    SocketError,
    Subscription,
    SyncResult,
)

router = APIRouter()
CUSTOMER_PROTOCOL = "nivaro.support.customer.v1"
STAFF_PROTOCOL = "nivaro.support.staff.v1"
MAX_MESSAGE_BYTES = 16384
RECHECK_SECONDS = 25


def read_frame(raw: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw)
    except (ValueError, RecursionError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def reference(raw: dict[str, object], name: str) -> UUID | None:
    value = raw.get(name)
    if isinstance(value, str) and len(value) <= 36:
        try:
            return UUID(value)
        except ValueError:
            pass
    return None


def failure(raw: dict[str, object], code: str) -> SocketError:
    return SocketError(
        type="error",
        schema_version=1,
        request_id=reference(raw, "request_id"),
        conversation_id=reference(raw, "conversation_id"),
        client_message_id=reference(raw, "client_message_id"),
        payload=FailureCode(code=code),
    )


async def handle_frame(
    db: Database,
    actor: Actor,
    frame: ClientMessage,
    stream: ConversationStream,
    activity: ActivitySession,
) -> ServerMessage | None:
    if isinstance(frame, ActivityFrame):
        if stream.conversation != frame.conversation_id:
            raise SupportError("support.subscription_required", 403)
        await activity.update(
            db,
            actor,
            frame.conversation_id,
            "typing" if frame.type == "typing.changed" else "presence",
            frame.payload.active,
        )
        stream.wake.set()
        return None
    if isinstance(frame, MessageSend):
        async with db.sessions() as session:
            stored = await send_message(
                session,
                actor,
                frame.conversation_id,
                SendMessage(client_message_id=frame.client_message_id, body=frame.payload.body),
            )
        return MessageAccepted(
            type="message.accepted",
            schema_version=1,
            request_id=frame.request_id,
            conversation_id=frame.conversation_id,
            client_message_id=frame.client_message_id,
            payload=Acceptance(
                message_id=stored.id, sequence=stored.sequence, created_at=stored.created_at
            ),
        )
    if isinstance(frame, MarkRead):
        async with db.sessions() as session:
            receipts = await mark_read(
                session, actor, frame.conversation_id, frame.payload.sequence
            )
        if frame.conversation_id == stream.conversation:
            stream.receipts = receipts
        return ReadChanged(
            type="message.read",
            schema_version=1,
            request_id=frame.request_id,
            conversation_id=frame.conversation_id,
            payload=receipts,
        )
    if isinstance(frame, Subscription):
        previous = stream.conversation
        page = await stream.subscribe(db, actor, frame.conversation_id, frame.payload.after)
        if previous != frame.conversation_id:
            await activity.leave()
    else:
        page = await history(db, actor, frame.conversation_id, frame.payload.after)
        if frame.conversation_id == stream.conversation:
            stream.receipts = page.receipts
    return SyncResult(
        type="sync.result",
        schema_version=1,
        request_id=frame.request_id,
        conversation_id=frame.conversation_id,
        payload=page,
    )


async def next_input(socket: WebSocket, wake: asyncio.Event) -> tuple[ASGIMessage | None, bool]:
    incoming = asyncio.create_task(socket.receive())
    notification = asyncio.create_task(wake.wait())
    try:
        await asyncio.wait(
            (incoming, notification), timeout=RECHECK_SECONDS, return_when=asyncio.FIRST_COMPLETED
        )
        event = incoming.result() if incoming.done() else None
        notified = wake.is_set()
        wake.clear()
        return event, notified
    finally:
        incoming.cancel()
        notification.cancel()
        await asyncio.gather(incoming, notification, return_exceptions=True)


async def forward(
    socket: WebSocket,
    db: Database,
    actor: Actor,
    stream: ConversationStream,
    activity: ActivitySession,
) -> None:
    conversation = stream.conversation
    if conversation is None:
        return
    try:
        page = await history(db, actor, conversation, stream.after)
    except SupportError as exc:
        if exc.status != 404:
            raise
        stream.close()
        await activity.leave()
        return
    async with asyncio.timeout(5):
        for message in page.messages:
            await socket.send_text(
                MessageCreated(
                    type="message.created",
                    schema_version=1,
                    conversation_id=conversation,
                    payload=message,
                ).model_dump_json()
            )
        if page.receipts != stream.receipts:
            await socket.send_text(
                ReadChanged(
                    type="message.read",
                    schema_version=1,
                    conversation_id=conversation,
                    request_id=None,
                    payload=page.receipts,
                ).model_dump_json()
            )
    stream.receipts = page.receipts
    stream.advance(page)
    for signal, duration in await activity.changes(db, actor, conversation):
        await send(
            socket,
            ActivityChanged(
                type="typing.changed" if signal == "typing" else "presence.changed",
                schema_version=1,
                conversation_id=conversation,
                payload=ActivityExpiry(expires_in_ms=duration),
            ),
        )
    if page.has_more:
        stream.wake.set()


@router.websocket("/ws/support")
async def support_socket(socket: WebSocket) -> None:
    origins = socket.headers.getlist("origin")
    if len(origins) != 1 or origins[0] not in socket.app.state.allowed_origins:
        await socket.close()
        return

    offered = socket.scope.get("subprotocols", [])
    kind: Kind = "customer"
    protocol = None
    if STAFF_PROTOCOL in offered:
        kind, protocol = "admin", STAFF_PROTOCOL
    elif CUSTOMER_PROTOCOL in offered:
        protocol = CUSTOMER_PROTOCOL
    elif offered:
        await socket.close()
        return

    authorization: IdentityAuthorization = socket.app.state.authorization
    database: Database = socket.app.state.database
    access = socket.cookies.get(f"nivaro_{kind}_access", "")
    try:
        await authorization.check_session(access, kind)
    except SupportError as exc:
        await socket.send_denial_response(Response(status_code=exc.status))
        return

    await socket.accept(subprotocol=protocol)
    stream = ConversationStream(socket.app.state.notifications)
    activity = ActivitySession(socket.app.state.activity_redis)
    try:
        while True:
            event, notified = await next_input(socket, stream.wake)
            raw: dict[str, object] = {}
            if event is not None:
                if event["type"] == "websocket.disconnect":
                    return
                text = event.get("text")
                if text is None:
                    await close(socket, 1003)
                    return
                if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
                    await close(socket, 1009)
                    return
                raw = read_frame(text)
            try:
                actor = await authorization.check_session(access, kind)
            except SupportError as exc:
                close_code = {401: 4401, 403: 4403}.get(exc.status, 1013)
                if event is not None:
                    await send(socket, failure(raw, exc.code))
                await close(socket, close_code)
                return
            if event is not None:
                try:
                    frame = CLIENT.validate_python(raw)
                    result = await handle_frame(database, actor, frame, stream, activity)
                except ValidationError:
                    result = failure(raw, "request.invalid")
                except SupportError as exc:
                    result = failure(raw, exc.code)
                except SQLAlchemyError:
                    result = failure(raw, "support.unavailable")
                if result is not None:
                    await send(socket, result)
            if notified or (event is None and activity.current is not None):
                if event is not None:
                    actor = await authorization.check_session(access, kind)
                await forward(socket, database, actor, stream, activity)
    except SupportError as exc:
        await close(socket, {401: 4401, 403: 4403}.get(exc.status, 1013))
    except (SQLAlchemyError, TimeoutError):
        await close(socket, 1013)
    except WebSocketDisconnect:
        return
    finally:
        stream.close()
        await activity.leave()


async def send(socket: WebSocket, frame: ServerMessage) -> None:
    await asyncio.wait_for(socket.send_text(frame.model_dump_json()), timeout=5)


async def close(socket: WebSocket, code: int) -> None:
    with suppress(TimeoutError, WebSocketDisconnect):
        await asyncio.wait_for(socket.close(code=code), timeout=1)
