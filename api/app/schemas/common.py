"""Shared response schemas."""
from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class OkEnvelope(BaseModel, Generic[T]):
    success: bool = True
    data: T


class ErrorEnvelope(BaseModel):
    success: bool = False
    error: Dict[str, Any]


class Pagination(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    total: int = Field(default=0, ge=0)


class PaginationEnvelope(BaseModel, Generic[T]):
    success: bool = True
    data: list[T]
    pagination: Pagination