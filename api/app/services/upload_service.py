"""Shared upload pipeline used by both authenticated and anonymous routes."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError, ErrorCode
from app.models.image import Image
from app.models.plan import Plan
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.services import credit_service
from app.services.image_processor import ProcessedImage, validate_and_process
from app.services.key_generator import generate_storage_key
from app.services.plan_service import compute_expires_at
from app.services.storage import get_storage


def _make_public_url(storage_key: str, ext: str) -> str:
    base = get_settings().public_image_base_url.rstrip("/")
    # The disk layout is sharded (/ab/cd/key.ext) — mirror that in the URL so
    # nginx can serve the file directly from the shared volume.
    return f"{base}/{storage_key[:2]}/{storage_key[2:4]}/{storage_key}.{ext}"


def perform_upload(
    db: Session,
    *,
    raw: bytes,
    original_filename: str,
    source: int,
    user: Optional[User],
    api_key_id: Optional[int],
) -> tuple[Image, ProcessedImage]:
    """End-to-end upload pipeline. Commits the transaction.

    Raises AppError with the appropriate error code on any failure.
    Returns the created Image record + processed payload info.
    """
    settings = get_settings()

    is_anon = user is None
    max_bytes = settings.anon_max_file_bytes if is_anon else settings.auth_max_file_bytes
    plan: Optional[Plan] = None
    if is_anon:
        # Anonymous uses anon_retention_days for expiry. No credit check.
        image_quality = Image.QUALITY_OPTIMIZED
        retention_days = settings.anon_retention_days
    else:
        plan = db.get(Plan, user.plan_id)
        if plan is None:
            raise AppError(ErrorCode.UNAUTHORIZED, "User has no plan assigned")
        image_quality = plan.image_quality
        retention_days = plan.retention_days
        # Credit gate (must run before doing expensive image processing)
        # The atomic decrement is deferred until after the file is written
        # to disk successfully, per PLAN §8.

    try:
        processed = validate_and_process(
            raw,
            max_pixels=settings.max_pixels,
            image_quality=image_quality,
            max_bytes=max_bytes,
        )
    except AppError:
        # Log a failed event
        db.add(
            UsageEvent(
                user_id=user.id if user else None,
                api_key_id=api_key_id,
                event_type=UsageEvent.TYPE_FAILED_UPLOAD,
                bytes=len(raw),
                metadata_json={"source": source, "reason": "validate_failed"},
            )
        )
        db.commit()
        raise

    storage_key = generate_storage_key()
    storage_svc = get_storage()
    try:
        storage_svc.save(storage_key, processed.extension, _BytesIO(raw=processed.data))
    except Exception as exc:  # noqa: BLE001
        db.add(
            UsageEvent(
                user_id=user.id if user else None,
                api_key_id=api_key_id,
                event_type=UsageEvent.TYPE_FAILED_UPLOAD,
                bytes=len(processed.data),
                metadata_json={"source": source, "reason": "storage_error", "detail": str(exc)[:200]},
            )
        )
        db.commit()
        raise AppError(ErrorCode.STORAGE_ERROR, "Failed to persist image", details={"reason": str(exc)[:200]}) from exc

    now = datetime.utcnow()
    expires_at = now + _td_days(retention_days)
    public_url = _make_public_url(storage_key, processed.extension)

    image = Image(
        user_id=user.id if user else None,
        storage_key=storage_key,
        original_filename=(original_filename or "")[:255],
        mime_type=processed.mime_type,
        size_bytes=len(processed.data),
        width=processed.width,
        height=processed.height,
        hash=processed.sha256_hex,
        public_url=public_url,
        source=source,
        image_quality=processed.image_quality,
        created=now,
        expires_at=expires_at,
    )
    db.add(image)
    db.flush()  # image.id có sẵn để dùng làm reference_id cho credit transaction

    if not is_anon:
        # Atomic credit decrement + audit row (sẽ raise QUOTA_EXCEEDED nếu hết).
        # Cần SELECT...FOR UPDATE để concurrent uploads không oversubscribe.
        from app.services.credit_service import consume_credit
        new_balance = consume_credit(
            db,
            user_id=user.id,
            reference_type="image",
            reference_id=image.id,
        )

    # Audit event
    db.add(
        UsageEvent(
            user_id=user.id if user else None,
            api_key_id=api_key_id,
            event_type=UsageEvent.TYPE_UPLOAD,
            bytes=len(processed.data),
            metadata_json={
                "source": source,
                "mime_type": processed.mime_type,
                "width": processed.width,
                "height": processed.height,
            },
        )
    )
    db.flush()
    # Balance đã được update + tx đã reference_id ở phần consume_credit phía trên.

    db.commit()
    db.refresh(image)
    return image, processed


class _BytesIO:
    """Tiny adapter to feed raw bytes into storage.save which expects a file-like."""

    def __init__(self, raw: bytes):
        import io
        self._buf = io.BytesIO(raw)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)


def _td_days(n: int):
    from datetime import timedelta
    return timedelta(days=n)