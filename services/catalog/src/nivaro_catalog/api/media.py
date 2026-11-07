"""Authenticated bounded binary uploads; originals never have a read route."""

import asyncio
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from nivaro_catalog.api.admin import DB
from nivaro_catalog.api.authorization import CatalogAdmin
from nivaro_catalog.api.schemas import ErrorEnvelope
from nivaro_catalog.application.administration import transaction
from nivaro_catalog.application.media import change_gallery, queue_image
from nivaro_catalog.infrastructure.media_storage import MAX_UPLOAD_BYTES, MediaStorage
from nivaro_catalog.infrastructure.models import MediaJobRow, MediaSlotRow, ProductRow
from nivaro_catalog.settings import Settings

router = APIRouter(
    tags=["catalog-media"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 413, 422, 503)},
)


class MediaJob(BaseModel):
    id: UUID
    state: Literal["uploaded", "processing", "ready", "failed"]
    error_code: str | None


class MediaSlot(BaseModel):
    position: int
    alt: dict[str, str]
    active: MediaJob | None
    pending: MediaJob | None
    urls: dict[str, str]
    image_kind: Literal["illustration", "exact_sku"] = "illustration"


class MediaGallery(BaseModel):
    version: int
    items: list[MediaSlot]


class GalleryChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(gt=0)
    destination: int | None = Field(default=None, ge=0, le=7)


class PublicImage(BaseModel):
    id: UUID
    alt: dict[str, str]
    urls: dict[str, str]
    image_kind: Literal["illustration", "exact_sku"]


def job_view(job: MediaJobRow | None) -> MediaJob | None:
    return MediaJob.model_validate(job, from_attributes=True) if job else None


@router.get("/api/v1/admin/catalog/products/{product_id}/images", operation_id="listProductImages")
async def gallery(product_id: UUID, auth: CatalogAdmin, db: DB) -> MediaGallery:
    # Keep the revision and slot view consistent with the activation transaction.
    product = await db.scalar(
        select(ProductRow).where(ProductRow.id == product_id).with_for_update(read=True)
    )
    if product is None:
        raise HTTPException(404, "Product not found")
    slots = await db.scalars(
        select(MediaSlotRow)
        .where(MediaSlotRow.product_id == product_id)
        .order_by(MediaSlotRow.position)
    )
    result = []
    for slot in slots:
        active = await db.get(MediaJobRow, slot.active_job_id) if slot.active_job_id else None
        pending = await db.get(MediaJobRow, slot.desired_job_id) if slot.desired_job_id else None
        result.append(
            MediaSlot(
                position=slot.position,
                alt=slot.alt,
                active=job_view(active),
                pending=job_view(pending),
                urls={
                    width: f"/api/v1/admin/catalog/images/{active.id}/{width}"
                    for width in active.outputs
                }
                if active
                else {},
                image_kind="exact_sku"
                if active and active.image_kind == "exact_sku"
                else "illustration",
            )
        )
    return MediaGallery(version=product.version, items=result)


@router.post(
    "/api/v1/admin/catalog/products/{product_id}/images/{position}/change",
    operation_id="changeProductGallery",
)
async def change(
    product_id: UUID,
    position: Annotated[int, Path(ge=0, le=7)],
    body: GalleryChange,
    auth: CatalogAdmin,
    db: DB,
    request: Request,
) -> dict[str, bool]:
    async with transaction(db, auth.user_id, request.state.request_id):
        await change_gallery(
            db,
            product_id=product_id,
            position=position,
            expected_version=body.expected_version,
            destination=body.destination,
            actor_id=auth.user_id,
            request_id=request.state.request_id,
        )
    return {"saved": True}


@router.get("/api/v1/catalog/products/{product_id}/images", operation_id="getProductGallery")
async def public_gallery(product_id: UUID, db: DB) -> list[PublicImage]:
    product = await db.get(ProductRow, product_id)
    if product is None or product.status != "published":
        raise HTTPException(404, "Product not found")
    rows = (
        await db.execute(
            select(MediaSlotRow, MediaJobRow)
            .join(MediaJobRow, MediaSlotRow.active_job_id == MediaJobRow.id)
            .where(MediaSlotRow.product_id == product_id, MediaJobRow.state == "ready")
            .order_by(MediaSlotRow.position)
        )
    ).all()
    return [
        PublicImage(
            id=job.id,
            alt=slot.alt,
            image_kind="exact_sku" if job.image_kind == "exact_sku" else "illustration",
            urls={width: f"/api/v1/catalog/images/{job.id}/{width}" for width in job.outputs},
        )
        for slot, job in rows
    ]


@router.put(
    "/api/v1/admin/catalog/products/{product_id}/images/{position}",
    status_code=202,
    operation_id="uploadProductImage",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def upload(
    product_id: UUID,
    position: Annotated[int, Path(ge=0, le=7)],
    auth: CatalogAdmin,
    db: DB,
    request: Request,
    expected_version: Annotated[int, Query(gt=0)],
    alt_fa: Annotated[str, Query(min_length=1, max_length=240)],
    alt_en: Annotated[str, Query(min_length=1, max_length=240)],
    image_kind: Literal["illustration", "exact_sku"] = "illustration",
) -> MediaJob:
    # Authorization is resolved before receiving binary bytes. Recheck the product
    # revision under lock after storage; never keep row locks across upload I/O.
    product = await db.get(ProductRow, product_id)
    if product is None:
        raise HTTPException(404, "Product not found")
    await db.rollback()
    content = bytearray()
    try:
        async with asyncio.timeout(30):
            async for chunk in request.stream():
                if len(content) + len(chunk) > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Image exceeds 8 MiB")
                content.extend(chunk)
    except TimeoutError as exc:
        raise HTTPException(408, "Image upload timed out") from exc
    if not content:
        raise HTTPException(422, "Empty image")
    settings = Settings()
    job_id = uuid4()
    try:
        storage = MediaStorage(settings.media_private_root, settings.media_output_root)
        await asyncio.to_thread(storage.write_original, job_id, bytes(content))
    except OSError as exc:
        raise HTTPException(503, "Image storage unavailable") from exc
    async with transaction(db, auth.user_id, request.state.request_id):
        await queue_image(
            db,
            product_id=product_id,
            position=position,
            expected_version=expected_version,
            job_id=job_id,
            actor_id=auth.user_id,
            alt={"fa": alt_fa, "en": alt_en},
            image_kind=image_kind,
            request_id=request.state.request_id,
        )
    return MediaJob(id=job_id, state="uploaded", error_code=None)


async def output_file(db: DB, job_id: UUID, width: int, *, public: bool) -> FileResponse:
    job = await db.get(MediaJobRow, job_id)
    if job is None or job.state != "ready" or str(width) not in job.outputs:
        raise HTTPException(404, "Image not found")
    slot = await db.get(MediaSlotRow, job.slot_id)
    product = await db.get(ProductRow, slot.product_id) if slot else None
    if (
        not product
        or not slot
        or slot.active_job_id != job.id
        or (public and product.status != "published")
    ):
        raise HTTPException(404, "Image not found")
    settings = Settings()
    root = settings.media_output_root.resolve()
    path = (root / job.outputs[str(width)]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Image not found")
    return FileResponse(
        path, media_type="image/webp", headers={"X-Content-Type-Options": "nosniff"}
    )


@router.get(
    "/api/v1/admin/catalog/images/{job_id}/{width}",
    operation_id="getAdminProductImage",
    response_class=FileResponse,
)
async def private_output(job_id: UUID, width: int, auth: CatalogAdmin, db: DB) -> FileResponse:
    return await output_file(db, job_id, width, public=False)


@router.get(
    "/api/v1/catalog/images/{job_id}/{width}",
    operation_id="getProductImage",
    response_class=FileResponse,
)
async def public_output(job_id: UUID, width: int, db: DB) -> FileResponse:
    return await output_file(db, job_id, width, public=True)
