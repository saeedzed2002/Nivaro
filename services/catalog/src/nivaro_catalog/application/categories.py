"""Serialize the small two-level taxonomy before checking parent/child invariants.

Advisory transaction lock (71404, 1) is reserved for category structural writes.
All future category writers must take it before any category row lock. Product
writes never acquire it; category deletion is intentionally not exposed.
"""

from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from nivaro_catalog.application.administration import Administration, snapshot
from nivaro_catalog.domain.administration import AdministrationError, CategoryContent, CategoryEdit
from nivaro_catalog.infrastructure.models import CategoryAuditRow, CategoryRow

FIELDS = ("slug", "name", "parent_id", "version")


async def save_category(
    service: Administration, command: CategoryContent, category_id: UUID | None = None
) -> UUID:
    db = service.db
    # One bounded staff transaction, after identity checks; never hold across network I/O.
    await db.execute(text("SELECT pg_advisory_xact_lock(71404, 1)"))
    row = None
    if category_id:
        row = await db.scalar(
            select(CategoryRow).where(CategoryRow.id == category_id).with_for_update()
        )
        if row is None:
            raise AdministrationError("catalog.category_not_found", "Category not found", 404)
        if not isinstance(command, CategoryEdit) or row.version != command.expected_version:
            raise AdministrationError(
                "catalog.category_version_conflict", "Category changed; reload before editing"
            )
    else:
        count = await db.scalar(select(func.count()).select_from(CategoryRow)) or 0
        if count >= 1000:
            raise AdministrationError(
                "catalog.category_limit", "At most 1000 categories are supported"
            )
    if command.parent_id:
        parent = await db.get(CategoryRow, command.parent_id)
        if parent is None:
            raise AdministrationError(
                "catalog.category_not_found", "Parent category not found", 422
            )
        has_children = category_id and await db.scalar(
            select(CategoryRow.id).where(CategoryRow.parent_id == category_id).limit(1)
        )
        if command.parent_id == category_id or parent.parent_id is not None or has_children:
            raise AdministrationError(
                "catalog.category_hierarchy",
                "Only two levels are allowed; preserve existing children",
            )
    before = snapshot(row, FIELDS) if row else {}
    if row is None:
        row = CategoryRow(id=uuid4(), version=1, image="showroom")
        db.add(row)
    row.slug, row.name, row.parent_id = (
        command.slug,
        {"fa": command.name.fa.strip(), "en": command.name.en.strip()},
        command.parent_id,
    )
    if before and before == snapshot(row, FIELDS):
        return row.id
    if before:
        row.version += 1
    await db.flush()
    db.add(
        CategoryAuditRow(
            id=uuid4(),
            category_id=row.id,
            actor_id=service.actor_id,
            target_id=row.id,
            action="category.edited" if before else "category.created",
            before=before,
            after=snapshot(row, FIELDS),
            reason="",
            request_id=service.request_id,
        )
    )
    return row.id
