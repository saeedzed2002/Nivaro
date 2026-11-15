import hmac
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import Tokens
from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.sessions import Sessions
from nivaro_identity.settings import Settings

SERVICE_TOKEN_PATH = "/internal/v1/service-tokens"
CHECKOUT_CONTEXT_PATH = "/internal/v1/orders/checkout-context"
router = APIRouter(include_in_schema=False)
basic = HTTPBasic(auto_error=False)
ORDERS_SERVICE_SCOPES = {
    "nivaro-catalog": frozenset({"catalog.quote", "catalog.reserve", "catalog.finalize"}),
    "nivaro-payments": frozenset(
        {"payments.start", "payments.read", "payments.verify", "payments.refund"}
    ),
}
ORDERS_DELEGATED_GRANTS = {
    ("nivaro-cart", "cart.checkout_snapshot"),
    ("nivaro-identity", "identity.address_snapshot"),
}


class ServiceGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audience: Annotated[str, Field(min_length=1, max_length=80)]
    scope: Annotated[str, Field(min_length=1, max_length=80)]
    customer_access: Annotated[SecretStr, Field(min_length=1, max_length=8192)] | None = None


class ServiceToken(BaseModel):
    access_token: str


def require_orders(request: Request, credentials: HTTPBasicCredentials | None) -> None:
    secret: str | None = request.app.state.orders_client_secret
    if (
        secret is None
        or credentials is None
        or credentials.username != "orders"
        or not hmac.compare_digest(credentials.password.encode(), secret.encode())
    ):
        raise IdentityError("service.unauthorized", 401)


@router.post(SERVICE_TOKEN_PATH)
async def issue_token(
    body: ServiceGrant,
    request: Request,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)],
) -> ServiceToken:
    require_orders(request, credentials)
    tokens: Tokens = request.app.state.sessions.tokens
    if body.scope in ORDERS_SERVICE_SCOPES.get(body.audience, ()):
        if body.customer_access is not None:
            raise IdentityError("service.forbidden", 403)
        return ServiceToken(access_token=tokens.issue_service("orders", body.audience, body.scope))
    if (body.audience, body.scope) not in ORDERS_DELEGATED_GRANTS or body.customer_access is None:
        raise IdentityError("service.forbidden", 403)
    database: Database = request.app.state.database
    sessions: Sessions = request.app.state.sessions
    async with database.sessions() as db:
        actor = await sessions.authenticate(db, body.customer_access.get_secret_value(), "customer")
    return ServiceToken(
        access_token=tokens.issue_service(
            "orders", body.audience, body.scope, customer_id=actor.user.id
        )
    )


class CheckoutMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    origin: Annotated[str, Field(min_length=1, max_length=256)]
    csrf_token: Annotated[SecretStr, Field(min_length=1, max_length=128)]


class CheckoutContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_access: Annotated[SecretStr, Field(min_length=1, max_length=8192)]
    mutation: CheckoutMutation | None = None


class CheckoutContext(BaseModel):
    customer_id: UUID
    cart_token: str | None = None
    address_token: str | None = None


@router.post(CHECKOUT_CONTEXT_PATH)
async def checkout_context(
    body: CheckoutContextRequest,
    request: Request,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)],
) -> CheckoutContext:
    require_orders(request, credentials)
    database: Database = request.app.state.database
    sessions: Sessions = request.app.state.sessions
    settings: Settings = request.app.state.settings
    async with database.sessions() as db:
        actor = await sessions.authenticate(db, body.customer_access.get_secret_value(), "customer")
        customer_id = actor.user.id
        if body.mutation is None:
            return CheckoutContext(customer_id=customer_id)
        if body.mutation.origin not in settings.allowed_origins:
            raise IdentityError("origin.forbidden", 403)
        sessions.check_csrf(actor.session, body.mutation.csrf_token.get_secret_value())

    return CheckoutContext(
        customer_id=customer_id,
        cart_token=sessions.tokens.issue_service(
            "orders", "nivaro-cart", "cart.checkout_snapshot", customer_id=customer_id
        ),
        address_token=sessions.tokens.issue_service(
            "orders", "nivaro-identity", "identity.address_snapshot", customer_id=customer_id
        ),
    )
