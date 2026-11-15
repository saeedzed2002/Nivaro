import asyncio
import json

import httpx


class UpstreamUnavailable(Exception):
    """The upstream did not return an expected, bounded JSON response."""


async def request_json(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    json_body: dict[str, object] | None = None,
    auth: tuple[str, str] | None = None,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    max_bytes: int = 16384,
) -> tuple[int, object]:
    try:
        async with asyncio.timeout(5):
            async with http.stream(
                method, url, json=json_body, auth=auth, headers=headers, params=params
            ) as response:
                body = bytearray()
                async for part in response.aiter_bytes(8192):
                    body.extend(part)
                    if len(body) > max_bytes:
                        raise UpstreamUnavailable()
                return response.status_code, json.loads(body)
    except (httpx.HTTPError, TimeoutError, ValueError) as exc:
        raise UpstreamUnavailable() from exc
