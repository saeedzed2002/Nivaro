from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.params import Depends

from nivaro_catalog.api.admin import DB
from nivaro_catalog.api.authorization import CheckoutScope, IdentityAuthorization
from nivaro_catalog.application import checkout
from nivaro_catalog.domain.checkout import Quote, QuoteRequest, Reservation, ReservationRequest

router = APIRouter(prefix="/internal/v1/catalog", include_in_schema=False)


def require(scope: CheckoutScope) -> Depends:
    async def authorize(request: Request) -> None:
        authorization: IdentityAuthorization = request.app.state.authorization
        await authorization.check_checkout(request.headers.get("authorization", ""), scope)

    return Depends(authorize)


@router.post("/quotes", dependencies=[require("catalog.quote")])
async def quote(body: QuoteRequest, db: DB) -> Quote:
    return await checkout.create_quote(db, body)


@router.post("/reservations", dependencies=[require("catalog.reserve")])
async def reserve(body: ReservationRequest, db: DB) -> Reservation:
    return await checkout.reserve(db, body)


@router.get("/reservations/{operation_id}", dependencies=[require("catalog.reserve")])
async def reservation(operation_id: UUID, customer_id: UUID, db: DB) -> Reservation:
    return await checkout.reservation_action(db, operation_id, customer_id, "read")


@router.post("/reservations/{operation_id}/{action}", dependencies=[require("catalog.finalize")])
async def finalize(
    operation_id: UUID,
    action: Literal["commit", "release", "commit-paid"],
    customer_id: UUID,
    db: DB,
) -> Reservation:
    return await checkout.reservation_action(db, operation_id, customer_id, action)
