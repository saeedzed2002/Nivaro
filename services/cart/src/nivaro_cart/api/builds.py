"""Private, market-bound build drafts and independent copies."""

from collections import Counter
from typing import Annotated, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nivaro_cart.api.errors import ERROR_RESPONSES
from nivaro_cart.api.items import Positive
from nivaro_cart.api.ownership import Actor, request_actor, resolve_owner
from nivaro_cart.domain.limits import validate_quantities
from nivaro_cart.domain.mutations import CartConflict, CartNotFound, Market
from nivaro_cart.infrastructure.database import Database
from nivaro_cart.infrastructure.models import Build, BuildLine

router = APIRouter(prefix="/api/v1/builds", tags=["builds"], responses=ERROR_RESPONSES)
Mode = Literal["complete_build", "parts_only"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SlotKey = Annotated[
    str,
    Field(
        pattern=r"^(cpu|motherboard|memory|storage|case|psu|cooler|gpu|monitor|keyboard|mouse|audio|chair|desk|accessory)(:[1-9][0-9]?)?$"
    ),
]
REPEATABLE = {"memory", "storage", "accessory"}


class BuildSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    slot_key: SlotKey
    variant_id: UUID
    quantity: Annotated[int, Field(strict=True, ge=1, le=10)] = 1

    @property
    def role(self) -> str:
        return self.slot_key.split(":", 1)[0]


class BuildContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    mode: Mode = "complete_build"
    requires_dedicated_gpu: StrictBool = False
    selections: Annotated[list[BuildSelection], Field(max_length=32)] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_slots(self) -> Self:
        if len({line.slot_key for line in self.selections}) != len(self.selections):
            raise ValueError("Slot keys must be unique")
        counts = Counter(line.role for line in self.selections)
        for line in self.selections:
            if line.role not in REPEATABLE and (line.quantity != 1 or counts[line.role] != 1):
                raise ValueError("This role accepts only one unit in one slot")
        return self


class CreateBuild(BuildContent):
    market: Market


class ReplaceBuild(BuildContent):
    expected_version: Positive


class DuplicateBuild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    expected_version: Positive


class BuildSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    market: Market
    currency: Literal["IRR", "USD"]
    mode: Mode
    requires_dedicated_gpu: bool
    version: int


class BuildView(BuildSummary):
    selections: list[BuildSelection]
    reserves_stock: Literal[False] = False


async def owned_build(
    db: AsyncSession, actor: Actor, build_id: UUID, *, version: int | None = None
) -> Build:
    owner = await resolve_owner(db, actor, mutating=version is not None)
    return await find_build(db, owner.id, build_id, version=version)


async def find_build(
    db: AsyncSession, owner_id: UUID, build_id: UUID, *, version: int | None = None
) -> Build:
    result = await db.scalar(
        select(Build).where(Build.id == build_id, Build.owner_id == owner_id).with_for_update()
    )
    if result is None:
        raise CartNotFound
    if version is not None and result.version != version:
        raise CartConflict("build.version_conflict", result.version)
    return result


async def selections_of(db: AsyncSession, build: Build) -> list[BuildSelection]:
    rows = await db.scalars(
        select(BuildLine).where(BuildLine.build_id == build.id).order_by(BuildLine.slot_key)
    )
    return [BuildSelection.model_validate(row) for row in rows]


def build_view(build: Build, selections: list[BuildSelection]) -> BuildView:
    return BuildView(**BuildSummary.model_validate(build).model_dump(), selections=selections)


async def insert_build(
    db: AsyncSession, build: Build, selections: list[BuildSelection]
) -> BuildView:
    db.add(build)
    await db.flush()
    db.add_all(BuildLine(build_id=build.id, **line.model_dump()) for line in selections)
    return build_view(build, selections)


@router.get("")
async def list_builds(
    request: Request,
    market: Market,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    after: UUID | None = None,
) -> list[BuildSummary]:
    actor = await request_actor(request)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor)
        query = select(Build).where(Build.owner_id == owner.id, Build.market == market)
        if after is not None:
            query = query.where(Build.id > after)
        rows = await db.scalars(query.order_by(Build.id).limit(limit))
        return [BuildSummary.model_validate(row) for row in rows]


@router.post("", status_code=201)
async def create_build(body: CreateBuild, request: Request) -> BuildView:
    actor = await request_actor(request, mutating=True)
    validate_quantities(
        ((line.variant_id, line.quantity) for line in body.selections),
        request.app.state.settings.limits(),
    )
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        owner = await resolve_owner(db, actor, mutating=True)
        build = Build(
            owner_id=owner.id,
            name=body.name,
            market=body.market,
            currency="IRR" if body.market == "ir" else "USD",
            mode=body.mode,
            requires_dedicated_gpu=body.requires_dedicated_gpu,
        )
        return await insert_build(db, build, body.selections)


@router.get("/{build_id}")
async def get_build(build_id: UUID, request: Request) -> BuildView:
    actor = await request_actor(request)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        build = await owned_build(db, actor, build_id)
        return build_view(build, await selections_of(db, build))


@router.patch("/{build_id}")
async def replace_build(build_id: UUID, body: ReplaceBuild, request: Request) -> BuildView:
    actor = await request_actor(request, mutating=True)
    validate_quantities(
        ((line.variant_id, line.quantity) for line in body.selections),
        request.app.state.settings.limits(),
    )
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        build = await owned_build(db, actor, build_id, version=body.expected_version)
        build.name, build.mode, build.requires_dedicated_gpu = (
            body.name,
            body.mode,
            body.requires_dedicated_gpu,
        )
        build.version += 1
        existing = {
            line.slot_key: line
            for line in await db.scalars(select(BuildLine).where(BuildLine.build_id == build.id))
        }
        for selection in body.selections:
            line = existing.pop(selection.slot_key, None)
            if line is None:
                db.add(BuildLine(build_id=build.id, **selection.model_dump()))
            else:
                line.variant_id, line.quantity = selection.variant_id, selection.quantity
        for omitted in existing.values():
            await db.delete(omitted)
        return build_view(build, body.selections)


@router.post("/{build_id}/duplicate", status_code=201)
async def duplicate_build(build_id: UUID, body: DuplicateBuild, request: Request) -> BuildView:
    actor = await request_actor(request, mutating=True)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        source = await owned_build(db, actor, build_id, version=body.expected_version)
        copy = Build(
            owner_id=source.owner_id,
            name=body.name,
            market=source.market,
            currency=source.currency,
            mode=source.mode,
            requires_dedicated_gpu=source.requires_dedicated_gpu,
        )
        return await insert_build(db, copy, await selections_of(db, source))


@router.delete("/{build_id}", status_code=204, response_class=Response)
async def delete_build(
    build_id: UUID, request: Request, expected_version: Annotated[int, Query(ge=1)]
) -> Response:
    actor = await request_actor(request, mutating=True)
    database: Database = request.app.state.database
    async with database.sessions.begin() as db:
        build = await owned_build(db, actor, build_id, version=expected_version)
        await db.delete(build)
    return Response(status_code=204)
