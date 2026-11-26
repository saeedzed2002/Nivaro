from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, Select, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_support.contracts import (
    Actor,
    Assignment,
    Conversation,
    ConversationPage,
    CreateConversation,
    History,
    Message,
    ReadState,
    SendMessage,
    StateChange,
    SupportError,
    UnansweredPage,
)
from nivaro_support.models import (
    AssignmentRow,
    ConversationRow,
    MessageOutboxRow,
    MessageRow,
    ReadCursorRow,
)


async def create_conversation(
    db: AsyncSession, actor: Actor, body: CreateConversation
) -> Conversation:
    async with db.begin():
        row = await db.scalar(
            insert(ConversationRow)
            .values(
                id=uuid4(),
                customer_id=actor.user_id,
                client_conversation_id=body.client_conversation_id,
                subject=body.subject,
            )
            .on_conflict_do_nothing(constraint="uq_support_conversation_request")
            .returning(ConversationRow)
        )
        if row is None:
            row = await db.scalar(
                select(ConversationRow).where(
                    ConversationRow.customer_id == actor.user_id,
                    ConversationRow.client_conversation_id == body.client_conversation_id,
                )
            )
            if row is None or row.subject != body.subject:
                raise SupportError("support.request_conflict", 409)
        return Conversation.model_validate(row)


def visible_conversations(actor: Actor) -> Select[ConversationRow]:
    scoped = select(ConversationRow)
    if actor.kind == "customer":
        scoped = scoped.where(ConversationRow.customer_id == actor.user_id)
    elif not actor.can_manage:
        scoped = scoped.where(
            or_(
                ConversationRow.assigned_agent_id == actor.user_id,
                ConversationRow.assigned_agent_id.is_(None) & (ConversationRow.status != "closed"),
            )
        )
    return scoped


async def list_conversations(
    db: AsyncSession, actor: Actor, before: UUID | None, limit: int, *, unanswered: bool = False
) -> ConversationPage:
    visible = visible_conversations(actor)
    scoped = visible
    if unanswered:
        latest_customer = (
            select(MessageRow.sequence)
            .where(
                MessageRow.conversation_id == ConversationRow.id,
                MessageRow.sequence == ConversationRow.last_sequence,
                MessageRow.sender_kind == "customer",
            )
            .exists()
        )
        scoped = scoped.where(ConversationRow.status != "closed", latest_customer)
    total = (
        await db.scalar(scoped.with_only_columns(func.count(), maintain_column_froms=True))
        if unanswered
        else None
    )
    if before is not None:
        boundary = await db.scalar(visible.where(ConversationRow.id == before))
        if boundary is None:
            raise SupportError("support.not_found", 404)
        scoped = scoped.where(
            tuple_(ConversationRow.created_at, ConversationRow.id)
            < tuple_(boundary.created_at, boundary.id)
        )
    rows = (
        await db.scalars(
            scoped.order_by(ConversationRow.created_at.desc(), ConversationRow.id.desc()).limit(
                limit + 1
            )
        )
    ).all()
    conversations = [Conversation.model_validate(row) for row in rows[:limit]]
    next_before = rows[limit - 1].id if len(rows) > limit else None
    if total is not None:
        return UnansweredPage(conversations=conversations, next_before=next_before, total=total)
    return ConversationPage(conversations=conversations, next_before=next_before)


async def require_conversation(
    db: AsyncSession,
    actor: Actor,
    conversation_id: UUID,
    *,
    reading: bool = False,
    claiming: bool = False,
) -> ConversationRow:
    query = select(ConversationRow).where(ConversationRow.id == conversation_id)
    if actor.kind == "customer":
        query = query.where(ConversationRow.customer_id == actor.user_id)
    elif not actor.can_manage:
        allowed: ColumnElement[bool] = ConversationRow.assigned_agent_id == actor.user_id
        if claiming:
            allowed = or_(allowed, ConversationRow.assigned_agent_id.is_(None))
        query = query.where(allowed)
    row = await db.scalar(query.with_for_update(read=reading))
    if row is None:
        raise SupportError("support.not_found", 404)
    return row


async def message_history(
    db: AsyncSession, actor: Actor, conversation_id: UUID, after: int, limit: int
) -> History:
    async with db.begin():
        row = await require_conversation(db, actor, conversation_id, reading=True)
        messages = (
            await db.scalars(
                select(MessageRow)
                .where(
                    MessageRow.conversation_id == row.id,
                    MessageRow.sequence > after,
                )
                .order_by(MessageRow.sequence)
                .limit(limit + 1)
            )
        ).all()
        return History(
            conversation=Conversation.model_validate(row),
            messages=[Message.model_validate(message) for message in messages[:limit]],
            has_more=len(messages) > limit,
            receipts=await read_state(db, actor, row),
        )


async def read_state(db: AsyncSession, actor: Actor, row: ConversationRow) -> ReadState:
    own = (actor.kind, actor.user_id)
    peer_id = row.assigned_agent_id if actor.kind == "customer" else row.customer_id
    peer_kind = "admin" if actor.kind == "customer" else "customer"
    peer = (peer_kind, peer_id) if peer_id is not None else None
    values = {
        (item.reader_kind, item.reader_id): item.sequence
        for item in await db.scalars(
            select(ReadCursorRow).where(
                ReadCursorRow.conversation_id == row.id,
                tuple_(ReadCursorRow.reader_kind, ReadCursorRow.reader_id).in_(
                    [own, peer] if peer is not None else [own]
                ),
            )
        )
    }
    return ReadState(
        own_sequence=values.get(own, 0),
        peer_sequence=values.get(peer, 0) if peer is not None else 0,
    )


async def mark_read(
    db: AsyncSession, actor: Actor, conversation_id: UUID, sequence: int
) -> ReadState:
    async with db.begin():
        row = await require_conversation(db, actor, conversation_id, reading=True)
        if sequence > row.last_sequence:
            raise SupportError("support.read_ahead", 422)
        if sequence:
            entry = insert(ReadCursorRow).values(
                conversation_id=row.id,
                reader_kind=actor.kind,
                reader_id=actor.user_id,
                sequence=sequence,
            )
            await db.execute(
                entry.on_conflict_do_update(
                    index_elements=[
                        ReadCursorRow.conversation_id,
                        ReadCursorRow.reader_kind,
                        ReadCursorRow.reader_id,
                    ],
                    set_={"sequence": entry.excluded.sequence},
                    where=ReadCursorRow.sequence < entry.excluded.sequence,
                )
            )
        return await read_state(db, actor, row)


async def assign(
    db: AsyncSession, actor: Actor, conversation_id: UUID, body: Assignment
) -> Conversation:
    if actor.kind != "admin" or (not actor.can_manage and body.agent_id != actor.user_id):
        raise SupportError("auth.forbidden", 403)
    async with db.begin():
        row = await require_conversation(db, actor, conversation_id, claiming=True)
        if row.assigned_agent_id == body.agent_id:
            return Conversation.model_validate(row)
        if row.status == "closed" or row.version != body.expected_version:
            raise SupportError("support.version_conflict", 409)
        previous = row.assigned_agent_id
        row.assigned_agent_id = body.agent_id
        row.version += 1
        db.add(
            AssignmentRow(
                conversation_id=row.id,
                version=row.version,
                actor_id=actor.user_id,
                previous_agent_id=previous,
                agent_id=body.agent_id,
            )
        )
        return Conversation.model_validate(row)


async def set_state(
    db: AsyncSession, actor: Actor, conversation_id: UUID, body: StateChange
) -> Conversation:
    async with db.begin():
        row = await require_conversation(db, actor, conversation_id)
        if row.status == body.status:
            return Conversation.model_validate(row)
        if row.version != body.expected_version:
            raise SupportError("support.version_conflict", 409)
        row.closed_at = (
            await db.scalar(select(func.clock_timestamp())) if body.status == "closed" else None
        )
        row.status = body.status
        row.version += 1
        return Conversation.model_validate(row)


async def send_message(
    db: AsyncSession, actor: Actor, conversation_id: UUID, body: SendMessage
) -> Message:
    async with db.begin():
        row = await require_conversation(db, actor, conversation_id)
        prior = await db.scalar(
            select(MessageRow).where(
                MessageRow.conversation_id == row.id,
                MessageRow.sender_id == actor.user_id,
                MessageRow.sender_kind == actor.kind,
                MessageRow.client_message_id == body.client_message_id,
            )
        )
        if prior is not None:
            if prior.body != body.body:
                raise SupportError("support.request_conflict", 409)
            return Message.model_validate(prior)
        if row.status == "closed":
            raise SupportError("support.closed", 409)
        # Serialize a sender's limit across conversations and replicas before reading the rate window.
        await db.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(str(actor.user_id), 1109)))
        )
        now = await db.scalar(select(func.clock_timestamp()))
        if now is None:
            raise SupportError("support.unavailable", 503)
        count = await db.scalar(
            select(func.count())
            .select_from(MessageRow)
            .where(
                MessageRow.sender_id == actor.user_id,
                MessageRow.created_at > now - timedelta(seconds=1),
            )
        )
        if count is not None and count >= 5:
            raise SupportError("support.rate_limited", 429)
        row.last_sequence += 1
        message = MessageRow(
            id=uuid4(),
            conversation_id=row.id,
            sender_id=actor.user_id,
            sender_kind=actor.kind,
            client_message_id=body.client_message_id,
            sequence=row.last_sequence,
            body=body.body,
            created_at=now,
        )
        db.add(message)
        await db.flush()
        db.add(MessageOutboxRow(message_id=message.id))
        return Message.model_validate(message)
