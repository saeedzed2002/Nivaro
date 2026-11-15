import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, ConfigDict, Field

from nivaro_identity.domain.errors import IdentityError
from nivaro_identity.domain.security import Tokens

SERVICE_TOKEN_PATH = "/internal/v1/service-tokens"
router = APIRouter(include_in_schema=False)
basic = HTTPBasic(auto_error=False)
ORDERS_CATALOG_SCOPES = frozenset({"catalog.quote", "catalog.reserve", "catalog.finalize"})


class ServiceGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audience: Annotated[str, Field(min_length=1, max_length=80)]
    scope: Annotated[str, Field(min_length=1, max_length=80)]


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
    if body.audience != "nivaro-catalog" or body.scope not in ORDERS_CATALOG_SCOPES:
        raise IdentityError("service.forbidden", 403)
    tokens: Tokens = request.app.state.sessions.tokens
    return ServiceToken(access_token=tokens.issue_service("orders", body.audience, body.scope))
