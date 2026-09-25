"""Image schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Base64ImageIn(BaseModel):
    image: str = Field(
        description="Either raw Base64 string or a data URI `data:image/png;base64,...`"
    )
    filename: Optional[str] = Field(default=None, max_length=255)


class ImageOut(BaseModel):
    id: int
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    public_url: str
    source: int
    image_quality: int
    created: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class UploadOut(BaseModel):
    id: int
    url: str
    mime_type: str
    size: int
    created_at: datetime