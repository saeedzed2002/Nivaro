from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from nivaro_cart.api.authorization import IdentityAuthorization
from nivaro_cart.api.ownership import GroupView
from nivaro_cart.domain.mutations import CartConflict, CartNotFound, Market
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.infrastructure.models import Cart, CartGroup, CartLine, Owner

router = APIRouter(prefix="/internal/v1/orders", include_in_schema=False)


class CheckoutLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    variant_id: UUID
    quantity: int
    group_id: UUID | None
    slot_key: str | None


class CheckoutGroup(GroupView):
    source_build_id: UUID | None
    source_build_version: int | None


class CheckoutCart(BaseModel):
    id: UUID
    version: int
    market: Market
    currency: Literal["IRR", "USD"]
    lines: list[CheckoutLine]
    groups: list[CheckoutGroup]


@router.get("/carts/{market}")
async def snapshot(
    market: Market, version: Annotated[int, Query(ge=1)], request: Request
) -> CheckoutCart:
    authorization: IdentityAuthorization = request.app.state.authorization
    customer_id = await authorization.snapshot_customer(request.headers.get("authorization", ""))
    database: Database = request.app.state.database
    async with database.sessions() as db, db.begin():
        # Cart writes take an exclusive lock on this row before changing children.
        cart = await db.scalar(
            select(Cart)
            .join(Owner, Owner.id == Cart.owner_id)
            .where(Owner.customer_id == customer_id, Cart.market == market)
            .with_for_update(read=True, of=Cart)
        )
        if cart is None:
            raise CartNotFound()
        if cart.version != version:
            raise CartConflict("cart.version_conflict", cart.version)
        lines = await db.scalars(
            select(CartLine).where(CartLine.cart_id == cart.id).order_by(CartLine.id)
        )
        groups = await db.scalars(
            select(CartGroup).where(CartGroup.cart_id == cart.id).order_by(CartGroup.id)
        )
        return CheckoutCart.model_validate(
            {
                "id": cart.id,
                "version": cart.version,
                "market": cart.market,
                "currency": cart.currency,
                "lines": [CheckoutLine.model_validate(line) for line in lines],
                "groups": [CheckoutGroup.model_validate(group) for group in groups],
            }
        )
