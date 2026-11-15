import asyncio
import hashlib
import json
from time import time
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import Request

from nivaro_support.contracts import Actor, Kind, SupportError


class IdentityAuthorization:
    def __init__(self, client: httpx.AsyncClient, key: str):
        if len(key) < 32:
            raise ValueError("Use a dedicated support identity key")
        self.client, self.key = client, key

    async def authenticate(
        self, request: Request, kind: Kind, target_agent_id: UUID | None = None
    ) -> Actor:
        access = request.cookies.get(f"nivaro_{kind}_access", "")
        if not access or len(access) > 8192:
            raise SupportError("auth.required", 401)
        mutating = request.method not in {"GET", "HEAD"}
        origin = request.headers.get("origin", "") if mutating else ""
        csrf = request.headers.get("x-csrf-token", "") if mutating else ""
        if mutating and (
            not origin
            or len(origin) > 256
            or not csrf
            or len(csrf) > 128
            or request.headers.get("sec-fetch-site") == "cross-site"
        ):
            raise SupportError("auth.forbidden", 403)
        body = {
            "access_token": access,
            "mutating": mutating,
            "origin": origin,
            "csrf_token": csrf,
            "kind": kind,
            "target_agent_id": str(target_agent_id) if target_agent_id else None,
        }
        issued = int(time())
        service = jwt.encode(
            {
                "iss": "nivaro-support",
                "sub": "support",
                "aud": "nivaro-identity-introspection",
                "kind": "service",
                "scope": "support.session_introspect",
                "iat": issued,
                "exp": issued + 30,
                "jti": str(uuid4()),
                "body_sha256": hashlib.sha256(
                    json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            },
            self.key,
            algorithm="HS256",
        )
        try:
            async with (
                asyncio.timeout(4),
                self.client.stream(
                    "POST",
                    "/internal/v1/support/session-check",
                    json=body,
                    headers={"Authorization": f"Bearer {service}"},
                ) as response,
            ):
                if response.status_code in (401, 403):
                    raise SupportError(
                        "auth.required" if response.status_code == 401 else "auth.forbidden",
                        response.status_code,
                    )
                if response.status_code != 200:
                    raise SupportError("auth.unavailable", 503)
                data = bytearray()
                async for chunk in response.aiter_bytes(2048):
                    data.extend(chunk)
                    if len(data) > 2048:
                        raise SupportError("auth.unavailable", 503)
                actor = Actor.model_validate_json(data)
                if actor.kind != kind or (actor.can_manage and kind != "admin"):
                    raise SupportError("auth.unavailable", 503)
                return actor
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            raise SupportError("auth.unavailable", 503) from exc
