from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_support.authorization import IdentityAuthorization
from nivaro_support.contracts import (
    Actor,
    Assignment,
    Conversation,
    ConversationPage,
    CreateConversation,
    ErrorEnvelope,
    History,
    Kind,
    Message,
    SendMessage,
    StateChange,
    SupportError,
)
from nivaro_support.conversations import (
    assign,
    create_conversation,
    list_conversations,
    message_history,
    send_message,
    set_state,
)
from nivaro_support.limits import BoundedBody
from nivaro_support.settings import Database, Settings
from nivaro_support.socket import router as socket_router

SCHEMA = "0001_support_conversations"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    app.state.allowed_origins = frozenset(settings.allowed_origins)
    app.state.database = database = Database(settings)
    key = settings.identity_key_file.read_text(encoding="utf-8").strip()
    try:
        async with httpx.AsyncClient(
            base_url=str(settings.identity_url), timeout=3, trust_env=False
        ) as client:
            app.state.authorization = IdentityAuthorization(client, key)
            yield
    finally:
        await database.engine.dispose()


app = FastAPI(
    title="Nivaro Support",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(BoundedBody)


@app.middleware("http")
async def request_identity(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.request_id = str(uuid4())
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def error(request: Request, status: int, code: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "request_id": request.state.request_id}}, status_code=status
    )


@app.exception_handler(SupportError)
async def support_error(request: Request, exc: SupportError) -> JSONResponse:
    return error(request, exc.status, exc.code)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error(request, 422, "request.invalid")


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return error(request, 503, "support.unavailable")


async def session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    async with database.sessions() as db:
        yield db


async def authenticated(request: Request) -> Actor:
    auth: IdentityAuthorization = request.app.state.authorization
    kind: Kind = "admin" if request.url.path.startswith("/api/v1/admin/") else "customer"
    return await auth.authenticate(request, kind)


DB = Annotated[AsyncSession, Depends(session)]
Principal = Annotated[Actor, Depends(authenticated)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[int, Query(ge=0, le=9223372036854775807)]
customer = APIRouter(
    prefix="/api/v1/support/conversations",
    tags=["support"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)
staff = APIRouter(
    prefix="/api/v1/admin/support/conversations",
    tags=["staff support"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422, 429, 503)},
)


@customer.post("", operation_id="createSupportConversation")
async def create(body: CreateConversation, db: DB, actor: Principal) -> Conversation:
    return await create_conversation(db, actor, body)


@customer.get("", operation_id="listOwnedSupportConversations")
@staff.get("", operation_id="listStaffSupportConversations")
async def listing(
    db: DB, actor: Principal, before: UUID | None = None, limit: PageSize = 20
) -> ConversationPage:
    return await list_conversations(db, actor, before, limit)


@customer.get("/{conversation_id}/messages", operation_id="readOwnedSupportHistory")
@staff.get("/{conversation_id}/messages", operation_id="readStaffSupportHistory")
async def history(
    conversation_id: UUID, db: DB, actor: Principal, after: Cursor = 0, limit: PageSize = 50
) -> History:
    return await message_history(db, actor, conversation_id, after, limit)


@customer.post("/{conversation_id}/messages", operation_id="sendCustomerSupportMessage")
@staff.post("/{conversation_id}/messages", operation_id="sendStaffSupportMessage")
async def send(conversation_id: UUID, body: SendMessage, db: DB, actor: Principal) -> Message:
    return await send_message(db, actor, conversation_id, body)


@staff.put("/{conversation_id}/assignment", operation_id="assignSupportConversation")
async def assignment(
    conversation_id: UUID, body: Assignment, db: DB, request: Request
) -> Conversation:
    auth: IdentityAuthorization = request.app.state.authorization
    actor = await auth.authenticate(request, "admin", body.agent_id)
    return await assign(db, actor, conversation_id, body)


@staff.put("/{conversation_id}/status", operation_id="setSupportConversationStatus")
async def status(
    conversation_id: UUID, body: StateChange, db: DB, actor: Principal
) -> Conversation:
    return await set_state(db, actor, conversation_id, body)


@app.get("/health/ready", include_in_schema=False)
async def ready(db: DB) -> dict[str, str]:
    if await db.scalar(text("SELECT version_num FROM alembic_version")) != SCHEMA:
        raise SupportError("support.unavailable", 503)
    return {"service": "support", "status": "ok", "schema": SCHEMA}


app.include_router(customer)
app.include_router(staff)
app.include_router(socket_router)
