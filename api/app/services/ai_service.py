"""Orchestrator cho AI image generation.

Pipeline:
  1. Đọc config từ bảng ``configs`` (api_url, api_key, default_model,
     credit_cost, timeout_seconds).
  2. Tính cost = credit_cost * n.
  3. ``SELECT ... FOR UPDATE`` trên User để atomically trừ credit
     (raise QUOTA_EXCEEDED nếu không đủ). Tạo audit row ``TYPE_AI_GENERATION``.
  4. Gọi ``ai_provider.generate_image(...)``. Lỗi → rollback + refund credit.
  5. Validate bytes đầu ra qua ``image_processor.validate_and_process``
     (magic bytes + pixel bomb + EXIF strip).
  6. Save sharded path trên disk, INSERT ``Image`` row với ``source=5``.
  7. INSERT ``UsageEvent(type=TYPE_AI_GENERATION)`` để audit.
  8. Trả về ``(Image, ProcessedImage, credits_remaining)``.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import AppError, ErrorCode
from app.models.config import Config
from app.models.image import Image
from app.models.plan import Plan
from app.models.usage_event import UsageEvent
from app.models.upload_credit import UploadCreditTransaction
from app.models.user import User
from app.services import credit_service
from app.services.ai_provider import generate_image
from app.services.image_processor import ProcessedImage, validate_and_process
from app.services.key_generator import generate_storage_key
from app.services.storage import get_storage


logger = logging.getLogger("imageurl.ai_service")


# ---- Defaults -------------------------------------------------------------

DEFAULT_CREDIT_COST = 5
DEFAULT_TIMEOUT_SECONDS = 60
MAX_BATCH_IMAGES = 4


# ---- Config helpers -------------------------------------------------------


def _read_cfg(db: Session, key: str, default: str = "") -> str:
    row = db.scalar(select(Config).where(Config.config_key == key))
    if row and row.config_value and row.config_value.strip():
        return row.config_value.strip()
    return default


def load_ai_config(db: Session) -> dict[str, Any]:
    """Đọc 6 config key cho AI provider. Trả về dict.

    Field ``enabled`` = True/False — feature flag tắt/mở endpoint.
    """

    api_url = _read_cfg(
        db, Config.KEY_AI_IMAGE_API_URL,
        "https://router.auto-socials.com/v1/images/generations",
    )
    api_key = _read_cfg(db, Config.KEY_AI_IMAGE_API_KEY, "")
    default_model = _read_cfg(
        db, Config.KEY_AI_IMAGE_DEFAULT_MODEL,
        "ag/gemini-3.1-flash-image",
    )
    try:
        credit_cost = int(_read_cfg(db, Config.KEY_AI_IMAGE_CREDIT_COST, str(DEFAULT_CREDIT_COST)))
    except ValueError:
        credit_cost = DEFAULT_CREDIT_COST
    credit_cost = max(1, credit_cost)

    try:
        timeout_s = int(_read_cfg(db, Config.KEY_AI_IMAGE_TIMEOUT_SECONDS, str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        timeout_s = DEFAULT_TIMEOUT_SECONDS
    timeout_s = max(5, min(timeout_s, 300))

    # Feature flag — accept "true"/"1"/"yes"/"on" (case-insensitive).
    enabled_raw = _read_cfg(db, Config.KEY_AI_IMAGE_ENABLED, "true").lower()
    enabled = enabled_raw in {"true", "1", "yes", "on"}

    return {
        "api_url": api_url,
        "api_key": api_key,
        "default_model": default_model,
        "credit_cost": credit_cost,
        "timeout_seconds": float(timeout_s),
        "enabled": enabled,
    }


# ---- Main pipeline --------------------------------------------------------


def _make_public_url(storage_key: str, ext: str) -> str:
    base = get_settings().public_image_base_url.rstrip("/")
    return f"{base}/{storage_key[:2]}/{storage_key[2:4]}/{storage_key}.{ext}"


async def generate_and_store(
    db: Session,
    *,
    user: User,
    api_key_id: Optional[int],
    prompt: str,
    size: Optional[str],
    quality: Optional[str],
    output_format: str,
) -> tuple[Image, ProcessedImage, int]:
    """End-to-end: provider → validate → save → Image row → audit.

    Commits the transaction. Raises ``AppError`` on any failure.
    Refunds credit nếu pipeline thất bại sau khi đã consume.

    Chỉ nhận các field client-controlled: ``prompt``, ``size``, ``quality``,
    ``output_format``. Model / n / background / image_detail bị khoá cứng —
    server luôn lấy từ config. ``n`` cố định = 1 (mỗi request = 1 ảnh).
    """
    settings = get_settings()
    n = 1  # Khoá cứng — không cho batch nhiều ảnh trong 1 request.

    cfg = load_ai_config(db)
    cost_per_image = cfg["credit_cost"]
    total_cost = cost_per_image * n

    # ---- Feature flag ----
    if not cfg["enabled"]:
        raise AppError(
            ErrorCode.AI_DISABLED,
            "AI image generation is currently disabled by the operator",
            details={"config_key": Config.KEY_AI_IMAGE_ENABLED},
        )

    # ---- Plan check (cần cho expires_at) ----
    plan = db.get(Plan, user.plan_id)
    if plan is None:
        raise AppError(ErrorCode.UNAUTHORIZED, "User has no plan assigned")
    image_quality = plan.image_quality
    retention_days = plan.retention_days

    # ---- Credit gate (SELECT FOR UPDATE) ----
    # Nếu fail, raise QUOTA_EXCEEDED — không có refund vì chưa consume.
    new_balance = credit_service.consume_credit(
        db,
        user_id=user.id,
        reference_type="ai_generation",
        reference_id=None,  # set sau khi có image.id
        amount=total_cost,
        type_=UploadCreditTransaction.TYPE_AI_GENERATION,
    )

    images_out: list[tuple[Image, ProcessedImage]] = []
    credits_spent_total = 0
    images_failed = 0
    image: Optional[Image] = None
    processed: Optional[ProcessedImage] = None

    try:
        # ---- Gọi provider ----
        # Map output_format (png/jpeg/webp) sang force_format (PNG/JPEG/WEBP)
        # để validate_and_process re-encode đúng format.
        force_format_map = {"png": "PNG", "jpeg": "JPEG", "webp": "WEBP"}
        force_fmt = force_format_map.get(output_format, "PNG")

        provider_kwargs = {
            "api_url": cfg["api_url"],
            "api_key": cfg["api_key"],
            "prompt": prompt,
            "model": cfg["default_model"],
            "n": n,
            "size": size,
            "quality": quality,
            "output_format": output_format,
            "timeout_seconds": cfg["timeout_seconds"],
        }

        raw_list = await generate_image(**provider_kwargs)

        # ---- Validate + save từng ảnh ----
        storage_svc = get_storage()
        now = datetime.utcnow()

        for idx, raw in enumerate(raw_list):
            try:
                proc = validate_and_process(
                    raw,
                    max_pixels=settings.max_pixels,
                    image_quality=image_quality,
                    max_bytes=settings.auth_max_file_bytes,
                    force_format=force_fmt,
                )
            except AppError as exc:
                images_failed += 1
                logger.warning("AI gen output #%d failed validation: %s", idx, exc.message)
                db.add(
                    UsageEvent(
                        user_id=user.id,
                        api_key_id=api_key_id,
                        event_type=UsageEvent.TYPE_FAILED_UPLOAD,
                        bytes=len(raw),
                        metadata_json={
                            "source": Image.SOURCE_AI_GENERATED,
                            "reason": f"ai_validate_failed:{exc.code.value}",
                            "batch_index": idx,
                        },
                    )
                )
                continue

            storage_key = generate_storage_key()
            try:
                storage_svc.save(storage_key, proc.extension, io.BytesIO(proc.data))
            except Exception as exc:  # noqa: BLE001
                images_failed += 1
                logger.warning("AI gen output #%d storage failed: %s", idx, exc)
                db.add(
                    UsageEvent(
                        user_id=user.id,
                        api_key_id=api_key_id,
                        event_type=UsageEvent.TYPE_FAILED_UPLOAD,
                        bytes=len(proc.data),
                        metadata_json={
                            "source": Image.SOURCE_AI_GENERATED,
                            "reason": "ai_storage_error",
                            "batch_index": idx,
                            "detail": str(exc)[:200],
                        },
                    )
                )
                continue

            expires_at = now + _td_days(retention_days)
            public_url = _make_public_url(storage_key, proc.extension)
            img_row = Image(
                user_id=user.id,
                storage_key=storage_key,
                original_filename=f"ai-{storage_key[:8]}.{proc.extension}",
                mime_type=proc.mime_type,
                size_bytes=len(proc.data),
                width=proc.width,
                height=proc.height,
                hash=proc.sha256_hex,
                public_url=public_url,
                source=Image.SOURCE_AI_GENERATED,
                image_quality=proc.image_quality,
                created=now,
                expires_at=expires_at,
            )
            db.add(img_row)
            db.flush()  # để có image.id

            # ---- Audit UsageEvent cho từng ảnh thành công ----
            db.add(
                UsageEvent(
                    user_id=user.id,
                    api_key_id=api_key_id,
                    event_type=UsageEvent.TYPE_AI_GENERATION,
                    bytes=len(proc.data),
                    metadata_json={
                        "image_id": img_row.id,
                        "model": provider_kwargs["model"],
                        "prompt_len": len(prompt),
                        "batch_index": idx,
                        "batch_size": n,
                        "output_format": output_format,
                    },
                )
            )
            images_out.append((img_row, proc))

        if not images_out:
            # Toàn bộ batch fail → refund toàn bộ credits đã consume.
            _refund(db, user.id, total_cost, reason="all_outputs_failed")
            db.commit()
            raise AppError(
                ErrorCode.AI_PROVIDER_ERROR,
                "AI provider returned no valid images",
                details={"requested": n, "failed": images_failed},
            )

        # Nếu 1 phần fail (vd: provider trả 2 ảnh, 1 lỗi) → refund cho phần fail.
        if images_failed > 0:
            refund = cost_per_image * images_failed
            _refund(db, user.id, refund, reason=f"partial_batch_failed:{images_failed}")
            new_balance = user.upload_credits  # đã được update trong _refund

        db.commit()
        # refresh images để có timestamps chính xác
        for img_row, _proc in images_out:
            db.refresh(img_row)

        # Trả ảnh đầu tiên (cho n=1; UI sẽ chỉ hiển thị 1)
        image, processed = images_out[0]
        return image, processed, user.upload_credits

    except AppError:
        # Refund toàn bộ nếu pipeline fail sau khi đã consume.
        try:
            _refund(db, user.id, total_cost, reason="pipeline_error")
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI gen unexpected error")
        try:
            _refund(db, user.id, total_cost, reason="unexpected_error")
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "AI generation failed unexpectedly",
            details={"reason": str(exc)[:200]},
        ) from exc


def _refund(
    db: Session,
    user_id: int,
    amount: int,
    *,
    reason: str,
) -> None:
    """Hoàn credit (dùng cho AI gen fail)."""
    if amount <= 0:
        return
    credit_service.grant_credits(
        db,
        user_id=user_id,
        amount=amount,
        type_=UploadCreditTransaction.TYPE_REFUND,
        reference_type="ai_generation_refund",
        reference_id=None,
    )
    db.add(
        UsageEvent(
            user_id=user_id,
            event_type=UsageEvent.TYPE_FAILED_UPLOAD,
            bytes=0,
            metadata_json={"reason": reason, "refund_amount": amount},
        )
    )
    logger.info("AI gen refund: user=%s amount=%s reason=%s", user_id, amount, reason)


def _td_days(n: int):
    from datetime import timedelta
    return timedelta(days=n)