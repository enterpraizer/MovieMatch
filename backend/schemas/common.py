from typing import Any

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    cursor: int | None = None
    limit: int = Field(default=20, ge=1, le=100)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)
