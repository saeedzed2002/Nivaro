import argparse
import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, TypeAdapter

from nivaro_support.contracts import Contract, History, Message, MessageBody, ReadState

Cursor = Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]


class ClientFrame(Contract):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    request_id: UUID
    conversation_id: UUID


class SendPayload(Contract):
    body: MessageBody


class MessageSend(ClientFrame):
    type: Literal["message.send"]
    client_message_id: UUID
    payload: SendPayload


class HistoryCursor(Contract):
    after: Cursor


class Subscription(ClientFrame):
    type: Literal["conversation.subscribe"]
    payload: HistoryCursor


class SyncRequest(ClientFrame):
    type: Literal["sync.request"]
    payload: HistoryCursor


class ReadCursor(Contract):
    sequence: Cursor


class MarkRead(ClientFrame):
    type: Literal["message.read"]
    payload: ReadCursor


class ServerFrame(Contract):
    schema_version: Literal[1]
    request_id: UUID
    conversation_id: UUID


class Acceptance(Contract):
    message_id: UUID
    sequence: int
    created_at: AwareDatetime


class MessageAccepted(ServerFrame):
    type: Literal["message.accepted"]
    client_message_id: UUID
    payload: Acceptance


class SyncResult(ServerFrame):
    type: Literal["sync.result"]
    payload: History


class MessageCreated(Contract):
    type: Literal["message.created"]
    schema_version: Literal[1]
    conversation_id: UUID
    payload: Message


class ReadChanged(Contract):
    type: Literal["message.read"]
    schema_version: Literal[1]
    conversation_id: UUID
    request_id: UUID | None
    payload: ReadState


class FailureCode(Contract):
    code: str


class SocketError(Contract):
    type: Literal["error"]
    schema_version: Literal[1]
    request_id: UUID | None
    conversation_id: UUID | None
    client_message_id: UUID | None
    payload: FailureCode


ClientMessage = Annotated[
    MessageSend | Subscription | SyncRequest | MarkRead, Field(discriminator="type")
]
ServerMessage = Annotated[
    MessageAccepted | MessageCreated | SyncResult | ReadChanged | SocketError,
    Field(discriminator="type"),
]
CLIENT = TypeAdapter[ClientMessage](ClientMessage)
SERVER = TypeAdapter[ServerMessage](ServerMessage)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, adapter in (("support-client-v1", CLIENT), ("support-server-v1", SERVER)):
        path = args.directory / f"{name}.json"
        schema = adapter.json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["title"] = name
        exported = json.dumps(schema, sort_keys=True, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != exported:
                raise SystemExit(f"WebSocket contract is stale: {path.name}")
        else:
            path.write_text(exported, encoding="utf-8")


if __name__ == "__main__":
    main()
