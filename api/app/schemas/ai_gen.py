"""AI Image Generation schemas.

Endpoint: ``POST /api/v1/ai/generations``.

Client chỉ được phép truyền ``prompt``, ``size``, ``quality``, ``output_format``.
Các field khác (model, n, background, image_detail) được khoá cứng — server
luôn dùng default từ DB config. Field lạ sẽ bị reject với 422.

Output: đồng bộ với ``UploadOut`` — ``{success, data: {url, storage_key,
expires_at}}`` để client dùng cùng parser như upload thường.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---- Request ---------------------------------------------------------------


class AIGenRequest(BaseModel):
    """Body cho POST /ai/generations.

    Chỉ các field sau được phép truyền — field khác sẽ bị reject (422):

      * ``prompt``         (required, 1–2000 chars)
      * ``size``           (optional, e.g. ``1024x1024``)
      * ``quality``        (optional, low/medium/high)
      * ``output_format``  (optional, png/jpeg/webp — default png)

    ``model``, ``n``, ``background``, ``image_detail`` bị khoá cứng ở server
    — luôn lấy từ ``configs`` table (KEY_AI_IMAGE_*).
    """

    # Forbid mọi field ngoài schema — trả 422 khi client gửi model/n/...
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Mô tả ảnh cần gen. Bắt buộc, 1-2000 ký tự.",
    )
    size: Optional[Literal["1024x1024", "1024x1536", "1536x1024", "auto"]] = Field(
        default=None,
        description="Kích thước ảnh output. 'auto' = provider tự chọn.",
    )
    quality: Optional[Literal["low", "medium", "high"]] = Field(
        default=None,
        description="Mức chất lượng. NULL = provider tự chọn.",
    )
    output_format: Literal["png", "jpeg", "webp"] = Field(
        default="png",
        description=(
            "Định dạng ảnh trả về. File trên storage LUÔN có đuôi đúng theo "
            "field này (vd: chọn 'jpeg' → file là .jpg)."
        ),
    )


# ---- Response --------------------------------------------------------------


class AIGenOut(BaseModel):
    """Response trả về cho client.

    Đồng bộ với ``UploadOut``: id, url, mime_type, size, created_at + thêm
    ``storage_key`` (để client tự build URL nếu cần) và ``expires_at`` (theo
    retention của plan).
    """

    id: int
    url: str
    storage_key: str
    mime_type: str
    size: int
    created_at: datetime
    expires_at: datetime
    credits_remaining: Optional[int] = Field(
        default=None,
        description="Số credit còn lại sau khi gen (cho UI hiển thị ngay).",
    )


class AIStatusOut(BaseModel):
    """Response cho GET /ai/status — feature flag bật/tắt."""

    enabled: bool