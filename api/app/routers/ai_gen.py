"""AI Image Generation endpoint.

``POST /api/v1/ai/generations``

Auth: JWT hoặc API key (giống upload thường — không cho anonymous).
Rate limit: 10 phút / IP để chống cost abuse (credit cost 5/ảnh).
NOTE: KHÔNG dùng ``@limiter.limit(...)`` decorator vì slowapi 0.1.9 wrap function
khiến FastAPI không nhận diện được Pydantic body. Rate limit tự áp dụng
inline bằng dict + sliding-window in-memory.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, DefaultDict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user_or_api_key
from app.errors import AppError, ErrorCode
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.ai_gen import AIGenOut, AIGenRequest, AIStatusOut
from app.schemas.common import OkEnvelope
from app.services.ai_service import generate_and_store, load_ai_config


router = APIRouter(prefix="/ai", tags=["ai"])


# ---- Inline rate limit (sliding window 10 phút / IP) ----
# Lưu timestamps của các request gần đây theo IP.
# Đủ cho single-instance deploy — production multi-instance cần Redis.
_RATE_LIMIT_WINDOW = 60.0 * 10  # 10 phút
_RATE_LIMIT_MAX = 10
_rate_log: DefaultDict[str, Deque[float]] = defaultdict(deque)
_rate_lock = Lock()


def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW
    with _rate_lock:
        bucket = _rate_log[client_ip]
        # Bỏ timestamps quá cũ
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_MAX:
            from slowapi.errors import RateLimitExceeded
            raise RateLimitExceeded(_RATE_LIMIT_MAX)
        bucket.append(now)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


@router.get("/status", response_model=OkEnvelope[AIStatusOut])
async def ai_status(db: Session = Depends(get_db)) -> OkEnvelope[AIStatusOut]:
    """Feature flag: AI generate có bật không. Public, không cần auth."""
    cfg = load_ai_config(db)
    return OkEnvelope(data=AIStatusOut(enabled=cfg["enabled"]))


@router.post(
    "/generations",
    response_model=OkEnvelope[AIGenOut],
    summary="Generate image from prompt via external AI provider",
)
async def ai_generate(
    request: Request,
    payload: AIGenRequest,
    db: Session = Depends(get_db),
    user_key=Depends(get_current_user_or_api_key),
) -> OkEnvelope[AIGenOut]:
    """Endpoint chính của AI Generate.

    Body là Pydantic model ``AIGenRequest`` — đặt làm tham số thứ 2 (sau
    ``request``) để FastAPI tự nhận diện là body parameter.
    """
    # ---- Rate limit (10/min/IP) ----
    _check_rate_limit(_client_ip(request))

    user: User
    api_key: ApiKey | None
    user, api_key = user_key
    # Bắt buộc đăng nhập — không cho anonymous (credit cost quá cao).
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, "Authentication required for AI generation")

    img, _processed, credits_remaining = await generate_and_store(
        db,
        user=user,
        api_key_id=api_key.id if api_key else None,
        prompt=payload.prompt,
        size=payload.size,
        quality=payload.quality,
        output_format=payload.output_format,
    )
    return OkEnvelope(
        data=AIGenOut(
            id=img.id,
            url=img.public_url,
            storage_key=img.storage_key,
            mime_type=img.mime_type,
            size=img.size_bytes,
            created_at=img.created,
            expires_at=img.expires_at,
            credits_remaining=credits_remaining,
        )
    )