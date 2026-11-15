import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from nivaro_support.models import (
    AssignmentRow,
    ConversationRow,
    MessageOutboxRow,
    MessageRow,
    ReadCursorRow,
)
from nivaro_support.retention import process_batch
from nivaro_support.settings import Database, Settings

pytestmark = pytest.mark.skipif(
    os.getenv("SUPPORT_DISPOSABLE_TESTS") != "1", reason="Disposable support stack required"
)


async def test_retention_preserves_recent_and_locked_history():
    settings = Settings(retention_days=180)
    assert settings.db_host.startswith("nivaro-support-qa-")
    database = Database(settings)
    owner, agent = uuid4(), uuid4()
    locked, expired, fresh, open_id, waiting = [(uuid4(), uuid4()) for _ in range(5)]
    try:
        async with database.sessions() as db, db.begin():
            now = await db.scalar(select(func.clock_timestamp()))
            for (conversation, message), state, age in (
                (locked, "closed", 200),
                (expired, "closed", 181),
                (fresh, "closed", 179),
                (open_id, "open", 200),
                (waiting, "waiting", 200),
            ):
                created = now - timedelta(days=age)
                db.add(
                    ConversationRow(
                        id=conversation,
                        customer_id=owner,
                        client_conversation_id=uuid4(),
                        subject="Disposable retention test",
                        status=state,
                        last_sequence=1,
                        assigned_agent_id=agent,
                        created_at=created,
                        closed_at=created if state == "closed" else None,
                    )
                )
                await db.flush()
                db.add(
                    MessageRow(
                        id=message,
                        conversation_id=conversation,
                        sender_id=owner,
                        sender_kind="customer",
                        client_message_id=uuid4(),
                        sequence=1,
                        body="Disposable text",
                        created_at=created,
                    )
                )
                await db.flush()
                db.add_all(
                    [
                        MessageOutboxRow(message_id=message, published_at=created),
                        AssignmentRow(
                            conversation_id=conversation, version=2, actor_id=agent, agent_id=agent
                        ),
                        ReadCursorRow(
                            conversation_id=conversation,
                            reader_kind="admin",
                            reader_id=agent,
                            sequence=1,
                            published_sequence=1,
                        ),
                    ]
                )
        preview = await process_batch(settings, 10)
        assert preview["matched_conversations"] == 2
        assert preview["deleted_conversations"] == 0

        async with database.sessions() as db, db.begin():
            assert await db.get(ConversationRow, locked[0], with_for_update=True)
            run = await process_batch(settings, 1, apply=True)
            assert run["deleted_conversations"] == 1
            assert await db.get(ConversationRow, expired[0]) is None
            assert await db.get(MessageRow, expired[1]) is None
            assert await db.get(MessageOutboxRow, expired[1]) is None
            assert await db.get(AssignmentRow, (expired[0], 2)) is None
            assert await db.get(ReadCursorRow, (expired[0], "admin", agent)) is None

        assert (await process_batch(settings, 10, apply=True))["deleted_conversations"] == 1
        assert (await process_batch(settings, 10, apply=True))["deleted_conversations"] == 0
        async with database.sessions() as db:
            assert await db.get(ConversationRow, locked[0]) is None
            for conversation, message in (fresh, open_id, waiting):
                assert await db.get(ConversationRow, conversation) is not None
                assert await db.get(MessageRow, message) is not None
    finally:
        await database.engine.dispose()
