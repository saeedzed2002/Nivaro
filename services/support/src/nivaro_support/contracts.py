from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Status = Literal["open", "waiting", "closed"]
Kind = Literal["customer", "admin"]
Version = Annotated[int, Field(strict=True, ge=1, le=2147483647)]
MessageBody = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000, pattern=r"^[^\x00]*$"),
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class Actor(Contract):
    user_id: UUID
    kind: Kind
    can_manage: bool


class CreateConversation(Contract):
    client_conversation_id: UUID
    subject: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=160, pattern=r"^[^\x00]*$"
        ),
    ]


class Assignment(Contract):
    agent_id: UUID
    expected_version: Version


class StateChange(Contract):
    status: Status
    expected_version: Version


class SendMessage(Contract):
    client_message_id: UUID
    body: MessageBody


class Conversation(Contract):
    id: UUID
    subject: str
    status: Status
    assigned_agent_id: UUID | None
    version: int
    last_sequence: int
    created_at: AwareDatetime
    closed_at: AwareDatetime | None


class ConversationPage(Contract):
    conversations: list[Conversation]
    next_before: UUID | None


class UnansweredPage(ConversationPage):
    total: int


class Message(Contract):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    sender_kind: Kind
    client_message_id: UUID
    sequence: int
    body: str
    created_at: AwareDatetime


class ReadState(Contract):
    own_sequence: int
    peer_sequence: int


class History(Contract):
    conversation: Conversation
    messages: list[Message]
    has_more: bool
    receipts: ReadState


class ErrorDetail(Contract):
    code: str
    request_id: str


class ErrorEnvelope(Contract):
    error: ErrorDetail


class SupportError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
