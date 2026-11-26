from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from nivaro_catalog.api.admin import DB
from nivaro_catalog.api.authorization import (
    AdminPrincipal,
    CustomerPrincipal,
    IdentityAuthorization,
)
from nivaro_catalog.api.schemas import ErrorEnvelope
from nivaro_catalog.application.reviews import (
    moderate_review,
    moderation_queue,
    own_review,
    public_reviews,
    save_review,
)
from nivaro_catalog.domain.reviews import (
    ModerationQueue,
    OwnReview,
    PublicReviews,
    ReviewDecision,
    ReviewInput,
    ReviewStatus,
    SavedReview,
)
from nivaro_catalog.infrastructure.models import ReviewRow

responses: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 503)
}
router = APIRouter(
    prefix="/api/v1/catalog/products/{product_id}/reviews", tags=["reviews"], responses=responses
)
staff = APIRouter(
    prefix="/api/v1/admin/catalog/reviews", tags=["review-moderation"], responses=responses
)
PageSize = Annotated[int, Query(ge=1, le=50)]


async def customer(request: Request) -> CustomerPrincipal:
    authorization: IdentityAuthorization = request.app.state.authorization
    return await authorization.check_customer(
        request.cookies.get("nivaro_customer_access", ""),
        mutating=request.method != "GET",
        origin=request.headers.get("origin", ""),
        csrf=request.headers.get("x-csrf-token", ""),
    )


async def moderator(request: Request) -> AdminPrincipal:
    authorization: IdentityAuthorization = request.app.state.authorization
    return await authorization.check(
        request.cookies.get("nivaro_admin_access", ""),
        mutating=request.method != "GET",
        origin=request.headers.get("origin", ""),
        csrf=request.headers.get("x-csrf-token", ""),
        moderating=True,
    )


ReviewCustomer = Annotated[CustomerPrincipal, Depends(customer)]
ReviewModerator = Annotated[AdminPrincipal, Depends(moderator)]


@router.get("", operation_id="listProductReviews")
async def list_reviews(
    product_id: UUID, db: DB, before: UUID | None = None, limit: PageSize = 20
) -> PublicReviews:
    return await public_reviews(db, product_id, before, limit)


@router.get("/mine", operation_id="readMyProductReview")
async def read_mine(product_id: UUID, auth: ReviewCustomer, db: DB) -> OwnReview:
    return OwnReview(review=await own_review(db, product_id, auth.user_id))


@router.put("/mine", operation_id="saveMyProductReview")
async def save_mine(
    product_id: UUID, body: ReviewInput, auth: ReviewCustomer, db: DB
) -> SavedReview:
    return await save_review(db, product_id, auth.user_id, body)


@staff.get("", operation_id="listReviewModerationQueue")
async def list_queue(
    auth: ReviewModerator,
    db: DB,
    status: ReviewStatus = "pending",
    before: UUID | None = None,
    limit: PageSize = 20,
) -> ModerationQueue:
    return await moderation_queue(db, status, before, limit)


class ReviewOverview(BaseModel):
    pending: int


@staff.get("/overview", operation_id="readReviewQueueOverview")
async def review_overview(auth: ReviewModerator, db: DB) -> ReviewOverview:
    count = await db.scalar(
        select(func.count()).select_from(ReviewRow).where(ReviewRow.status == "pending")
    )
    return ReviewOverview(pending=count or 0)


@staff.post("/{review_id}/decision", operation_id="moderateProductReview")
async def decide(
    review_id: UUID, body: ReviewDecision, auth: ReviewModerator, db: DB
) -> SavedReview:
    return await moderate_review(db, review_id, auth.user_id, body)
