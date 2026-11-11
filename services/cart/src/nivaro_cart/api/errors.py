from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    current_version: int | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorEnvelope} for code in (401, 403, 404, 408, 409, 413, 422, 503)
}
