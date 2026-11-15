from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_catalog.domain.administration import AdministrationError
from nivaro_catalog.domain.reviews import (
    ModerationQueue,
    PublicReview,
    PublicReviews,
    ReviewDecision,
    ReviewInput,
    ReviewStatus,
    SavedReview,
)
from nivaro_catalog.infrastructure.models import (
    ProductRow,
    PurchaseEntitlementRow,
    ReviewDecisionRow,
    ReviewRow,
)


def version_conflict() -> AdministrationError:
    return AdministrationError("review.version_conflict", "The review version changed", 409)


async def require_public_product(
    db: AsyncSession, product_id: UUID, *, editing: bool = False
) -> None:
    product = select(ProductRow.id).where(
        ProductRow.id == product_id,
        ProductRow.status == "published",
        ProductRow.image_ready.is_(True),
    )
    if editing:
        product = product.with_for_update(read=True)
    if await db.scalar(product) is None:
        raise AdministrationError("catalog.not_found", "Product not found", 404)


verified_purchase = (
    select(PurchaseEntitlementRow.product_id)
    .where(
        PurchaseEntitlementRow.product_id == ReviewRow.product_id,
        PurchaseEntitlementRow.customer_id == ReviewRow.customer_id,
    )
    .correlate(ReviewRow)
    .exists()
)
moderation_reason = (
    select(ReviewDecisionRow.reason)
    .where(
        ReviewDecisionRow.review_id == ReviewRow.id, ReviewDecisionRow.version == ReviewRow.version
    )
    .correlate(ReviewRow)
    .scalar_subquery()
)


def public_view(row: ReviewRow, verified: bool) -> PublicReview:
    return PublicReview(
        id=row.id,
        rating=row.rating,
        body=row.body,
        created_at=row.created_at,
        verified_purchase=verified,
    )


def saved_view(row: ReviewRow, verified: bool, reason: str | None) -> SavedReview:
    return SavedReview(
        **public_view(row, verified).model_dump(),
        product_id=row.product_id,
        status=cast(ReviewStatus, row.status),
        version=row.version,
        moderation_reason=reason,
    )


async def page_before[*Columns](
    db: AsyncSession,
    query: Select[*Columns],
    scoped: Select[ReviewRow],
    before: UUID | None,
    limit: int,
) -> Select[*Columns]:
    if before is not None:
        boundary = await db.scalar(scoped.where(ReviewRow.id == before))
        if boundary is None:
            raise AdministrationError("review.cursor_not_found", "Review cursor not found", 404)
        query = query.where(
            tuple_(ReviewRow.created_at, ReviewRow.id) < tuple_(boundary.created_at, boundary.id)
        )
    return query.order_by(ReviewRow.created_at.desc(), ReviewRow.id.desc()).limit(limit + 1)


async def public_reviews(
    db: AsyncSession, product_id: UUID, before: UUID | None, limit: int
) -> PublicReviews:
    await require_public_product(db, product_id)
    conditions = (ReviewRow.product_id == product_id, ReviewRow.status == "approved")
    query = await page_before(
        db,
        select(ReviewRow, verified_purchase).where(*conditions),
        select(ReviewRow).where(*conditions),
        before,
        limit,
    )
    rows = (await db.execute(query)).all()
    count, average = (
        await db.execute(select(func.count(), func.avg(ReviewRow.rating)).where(*conditions))
    ).one()
    return PublicReviews(
        reviews=[public_view(row, verified) for row, verified in rows[:limit]],
        next_before=rows[limit - 1][0].id if len(rows) > limit else None,
        count=count,
        average_rating=round(float(average), 2) if average is not None else None,
    )


async def own_review(db: AsyncSession, product_id: UUID, customer_id: UUID) -> SavedReview | None:
    await require_public_product(db, product_id)
    result = (
        await db.execute(
            select(ReviewRow, verified_purchase, moderation_reason).where(
                ReviewRow.product_id == product_id, ReviewRow.customer_id == customer_id
            )
        )
    ).one_or_none()
    return saved_view(*result) if result is not None else None


async def read_saved(db: AsyncSession, row: ReviewRow) -> SavedReview:
    verified, reason = (
        await db.execute(
            select(verified_purchase, moderation_reason)
            .select_from(ReviewRow)
            .where(ReviewRow.id == row.id)
        )
    ).one()
    return saved_view(row, verified, reason)


async def save_review(
    db: AsyncSession, product_id: UUID, customer_id: UUID, body: ReviewInput
) -> SavedReview:
    async with db.begin():
        await require_public_product(db, product_id, editing=True)
        if body.expected_version == 0:
            inserted = await db.scalar(
                insert(ReviewRow)
                .values(
                    id=uuid4(),
                    product_id=product_id,
                    customer_id=customer_id,
                    rating=body.rating,
                    body=body.body,
                )
                .on_conflict_do_nothing(constraint="uq_product_customer_review")
                .returning(ReviewRow)
            )
            if inserted is not None:
                return await read_saved(db, inserted)
        row = await db.scalar(
            select(ReviewRow)
            .where(ReviewRow.product_id == product_id, ReviewRow.customer_id == customer_id)
            .with_for_update()
        )
        if row is None:
            raise version_conflict()
        if (row.rating, row.body) != (body.rating, body.body):
            if row.version != body.expected_version:
                raise version_conflict()
            row.rating, row.body, row.status = body.rating, body.body, "pending"
            row.version += 1
            await db.flush()
        return await read_saved(db, row)


async def moderation_queue(
    db: AsyncSession, status: ReviewStatus, before: UUID | None, limit: int
) -> ModerationQueue:
    query = await page_before(
        db,
        select(ReviewRow, verified_purchase, moderation_reason).where(ReviewRow.status == status),
        select(ReviewRow),
        before,
        limit,
    )
    rows = (await db.execute(query)).all()
    return ModerationQueue(
        reviews=[saved_view(*result) for result in rows[:limit]],
        next_before=rows[limit - 1][0].id if len(rows) > limit else None,
    )


async def moderate_review(
    db: AsyncSession, review_id: UUID, actor: UUID, decision: ReviewDecision
) -> SavedReview:
    async with db.begin():
        row = await db.get(ReviewRow, review_id, with_for_update=True)
        if row is None:
            raise AdministrationError("review.not_found", "Review not found", 404)
        if row.version != decision.expected_version:
            prior = await db.get(ReviewDecisionRow, (row.id, row.version))
            if (
                row.version == decision.expected_version + 1
                and prior is not None
                and (prior.actor_id, prior.status, prior.reason)
                == (actor, decision.status, decision.reason)
            ):
                return await read_saved(db, row)
            raise version_conflict()
        if row.status == decision.status:
            raise AdministrationError(
                "review.already_moderated", "The review already has this status", 409
            )
        row.status = decision.status
        row.version += 1
        db.add(
            ReviewDecisionRow(
                review_id=row.id,
                version=row.version,
                actor_id=actor,
                status=decision.status,
                reason=decision.reason,
            )
        )
        await db.flush()
        return await read_saved(db, row)
