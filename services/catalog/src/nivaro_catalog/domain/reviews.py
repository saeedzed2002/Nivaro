from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

ReviewStatus = Literal["pending", "approved", "rejected"]
Version = Annotated[int, Field(strict=True, ge=1, le=2147483647)]
Rating = Annotated[int, Field(strict=True, ge=1, le=5)]


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: Rating
    body: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=2000, pattern=r"^[^\x00]*$"
        ),
    ]
    expected_version: Annotated[int, Field(strict=True, ge=0, le=2147483647)]


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["approved", "rejected"]
    reason: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=400, pattern=r"^[^\x00]*$"
        ),
    ]
    expected_version: Version


class PublicReview(BaseModel):
    id: UUID
    rating: Rating
    body: str
    created_at: AwareDatetime
    verified_purchase: bool


class SavedReview(PublicReview):
    product_id: UUID
    version: Version
    status: ReviewStatus
    moderation_reason: str | None


class PublicReviews(BaseModel):
    reviews: list[PublicReview]
    next_before: UUID | None
    count: int
    average_rating: float | None


class OwnReview(BaseModel):
    review: SavedReview | None


class ModerationQueue(BaseModel):
    reviews: list[SavedReview]
    next_before: UUID | None
