import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import Tokens
from nivaro_identity.infrastructure.database import Database
from nivaro_identity.infrastructure.sessions import Sessions

SERVICE_TOKEN_PATH = "/internal/v1/service-tokens"
router = APIRouter(include_in_schema=False)
basic = HTTPBasic(auto_error=False)
ORDERS_CATALOG_SCOPES = frozenset({"catalog.quote", "catalog.reserve", "catalog.finalize"})
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


@router.post(SERVICE_TOKEN_PATH)
async def issue_token(
    body: ServiceGrant,
    request: Request,
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)],
) -> ServiceToken:
    secret: str | None = request.app.state.orders_client_secret
    if (
        secret is None
        or credentials is None
        or credentials.username != "orders"
        or not hmac.compare_digest(credentials.password.encode(), secret.encode())
    ):
        raise IdentityError("service.unauthorized", 401)
    tokens: Tokens = request.app.state.sessions.tokens
    if body.audience == "nivaro-catalog" and body.scope in ORDERS_CATALOG_SCOPES:
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
