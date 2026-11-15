import argparse
import asyncio
import json
from datetime import UTC, timedelta

from sqlalchemy import delete, func, select

from nivaro_support.models import (
    AssignmentRow,
    ConversationRow,
    MessageOutboxRow,
    MessageRow,
    ReadCursorRow,
)
from nivaro_support.settings import Database, Settings


async def process_batch(
    settings: Settings, batch_size: int, *, apply: bool = False
) -> dict[str, int | str | bool]:
    if not 1 <= batch_size <= 100:
        raise ValueError("Retention batch size must be between 1 and 100")
    db = Database(settings)
    try:
        async with db.sessions() as session, session.begin():
            now = await session.scalar(select(func.clock_timestamp()))
            if now is None:
                raise RuntimeError("Support database clock was unavailable")
            cutoff = now.astimezone(UTC) - timedelta(days=settings.retention_days)
            candidates = (
                select(ConversationRow.id)
                .where(ConversationRow.status == "closed", ConversationRow.closed_at <= cutoff)
                .order_by(ConversationRow.closed_at, ConversationRow.id)
                .limit(batch_size)
            )
            if apply:
                candidates = candidates.with_for_update(skip_locked=True)
            conversation_ids = (await session.scalars(candidates)).all()
            if apply and conversation_ids:
                message_ids = select(MessageRow.id).where(
                    MessageRow.conversation_id.in_(conversation_ids)
                )
                await session.execute(
                    delete(MessageOutboxRow).where(MessageOutboxRow.message_id.in_(message_ids))
                )
                await session.execute(
                    delete(ReadCursorRow).where(ReadCursorRow.conversation_id.in_(conversation_ids))
                )
                await session.execute(
                    delete(AssignmentRow).where(AssignmentRow.conversation_id.in_(conversation_ids))
                )
                await session.execute(
                    delete(MessageRow).where(MessageRow.conversation_id.in_(conversation_ids))
                )
                await session.execute(
                    delete(ConversationRow).where(ConversationRow.id.in_(conversation_ids))
                )
        return {
            "cutoff": cutoff.isoformat(),
            "applied": apply,
            "retention_days": settings.retention_days,
            "matched_conversations": len(conversation_ids),
            "deleted_conversations": len(conversation_ids) if apply else 0,
        }
    finally:
        await db.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or apply one bounded support-retention batch."
    )
    parser.add_argument(
        "--batch-size", type=int, default=25, choices=range(1, 101), metavar="1..100"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Delete eligible conversations and dependent history."
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(process_batch(Settings(), args.batch_size, apply=args.apply))))


if __name__ == "__main__":
    main()
