"""Payments — tạo đơn SePay QR + polling trạng thái + danh sách lịch sử.

Luồng SePay QR (theo docs):
    1. User chọn gói → POST /payments/upgrade → backend tạo Payment(status=pending),
       QR SePay, trả về {qr_image_url, code, expires_at}.
    2. Frontend hiển thị QR cho user quét.
    3. User mở app ngân hàng, chuyển khoản với nội dung = ``code`` trả về.
    4. SePay gửi webhook về /api/v1/webhooks/sepay (xem routers/sepay_webhook.py).
    5. Backend cập nhật payment → STATUS_COMPLETED + grant credits / upgrade plan.
    6. Frontend poll GET /payments/{id}/status mỗi 2-3s. Khi ``is_paid=true`` → redirect.

Endpoint ``/topup`` (mua credit lẻ) chưa kích hoạt SePay trong MVP — trả 501 nếu
client gọi. Giữ schema PaymentOut / PaymentUpgradeIn để dashboard có thể gọi.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status as _status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.errors import AppError, ErrorCode
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.user import User
from app.schemas.common import OkEnvelope
from app.schemas.usage import (
    PaymentOut,
    PaymentUpgradeIn,
    SepayConfigOut,
    SepayOrderOut,
    SepayStatusOut,
)
from app.services.sepay import (
    build_payment_description,
    build_qr_url,
    load_sepay_account,
    load_vietqr_store,
    slug_code,
)


logger = logging.getLogger("imageurl.payments")
router = APIRouter(prefix="/payments", tags=["payments"])


# ============== SePay config (public) ==============

@router.get("/sepay-config", response_model=OkEnvelope[SepayConfigOut])
def get_sepay_config(db: Session = Depends(get_db)) -> OkEnvelope[SepayConfigOut]:
    """Trả về thông tin SePay cho frontend (KHÔNG lộ secret)."""
    acc = load_sepay_account(db)
    return OkEnvelope(data=SepayConfigOut(
        bank_code=acc.bank_code,
        account_number=acc.account_number,
        account_name=acc.account_name,
        template=acc.template,
        qr_ttl_minutes=acc.qr_ttl_minutes,
    ))


# ============== Tạo đơn SePay QR (plan upgrade) ==============

@router.post("/upgrade", response_model=OkEnvelope[SepayOrderOut])
def upgrade(
    payload: PaymentUpgradeIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> OkEnvelope[SepayOrderOut]:
    """Tạo đơn SePay QR để nâng cấp plan.

    Trả về ảnh QR + nội dung CK + expires_at. Frontend hiển thị cho user quét,
    sau đó poll /payments/{id}/status để biết khi nào webhook xác nhận.
    """
    target = db.get(Plan, payload.plan_id)
    if not target:
        raise AppError(ErrorCode.IMAGE_NOT_FOUND, "Plan not found")

    current_plan = db.get(Plan, current.plan_id) if current.plan_id else None
    if current_plan and target.sort_order < current_plan.sort_order:
        raise AppError(
            ErrorCode.CONFLICT,
            f"Plan cannot be downgraded. Current: {current_plan.name}.",
        )

    if target.price <= 0:
        raise AppError(ErrorCode.VALIDATION_ERROR, "Free plan does not require payment")

    acc = load_sepay_account(db)
    if not acc.account_number:
        raise AppError(
            ErrorCode.CONFLICT,
            "SePay is not configured (missing bank account). "
            "Set SEPAY_ACCOUNT env var or add sepay.account_number in the configs table.",
        )

    code = slug_code()             # 8-char alphanumeric
    description = build_payment_description(code=code)
    amount_vnd = int(target.price) // 100  # xu → VND
    expires_at = datetime.utcnow() + timedelta(minutes=acc.qr_ttl_minutes)

    qr_url = build_qr_url(
        bank_code=acc.bank_code,
        account_number=acc.account_number,
        amount_vnd=amount_vnd,
        description=description,
        account_name=acc.account_name,
        template=acc.template,
        store_name=load_vietqr_store(db),
    )

    payment = Payment(
        user_id=current.id,
        type=Payment.TYPE_PLAN_UPGRADE,
        amount=target.price,           # xu
        currency="VND",
        status=Payment.STATUS_PENDING,
        provider="sepay",
        reference_type="plan",
        reference_id=target.id,
        code=description,
        plan_id=target.id,
        qr_payload=qr_url,
        sepay_account_number=acc.account_number,
        expires_at=expires_at,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    logger.info(
        "created SePay order: payment_id=%s user=%s code=%s amount_vnd=%s expires_at=%s",
        payment.id, current.id, description, amount_vnd, expires_at.isoformat(),
    )

    return OkEnvelope(data=SepayOrderOut(
        payment=PaymentOut.model_validate(payment),
        qr_image_url=qr_url,
        bank_code=acc.bank_code,
        account_number=acc.account_number,
        account_name=acc.account_name,
        amount_vnd=amount_vnd,
        description=description,
        expires_at=expires_at,
        seconds_remaining=acc.qr_ttl_minutes * 60,
    ))


# ============== Polling trạng thái (frontend gọi 2-3s/lần) ==============

@router.get("/{payment_id}/status", response_model=OkEnvelope[SepayStatusOut])
def payment_status(
    payment_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> OkEnvelope[SepayStatusOut]:
    """Polling trạng thái 1 đơn thanh toán. Idempotent + nhẹ."""
    payment = db.get(Payment, payment_id)
    if not payment or payment.user_id != current.id:
        raise AppError(ErrorCode.IMAGE_NOT_FOUND, "Payment not found")

    # Lazy expire khi frontend poll quá expires_at (cleanup cron chạy nền)
    is_expired = False
    if payment.status == Payment.STATUS_PENDING and payment.expires_at and payment.expires_at < datetime.utcnow():
        payment.status = Payment.STATUS_EXPIRED
        db.commit()
        is_expired = True
        logger.info("payment %s expired (lazy)", payment.id)

    return OkEnvelope(data=SepayStatusOut(
        payment_id=payment.id,
        status=payment.status,
        is_paid=payment.status == Payment.STATUS_COMPLETED,
        is_expired=is_expired or payment.status == Payment.STATUS_EXPIRED,
        paid_at=payment.paid_at,
        plan_id=payment.plan_id,
        credits=payment.credits,
    ))


# ============== Lịch sử thanh toán ==============

@router.get("", response_model=OkEnvelope[list[PaymentOut]])
def list_payments(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> OkEnvelope[list[PaymentOut]]:
    rows = db.scalars(
        select(Payment).where(Payment.user_id == current.id).order_by(Payment.created.desc())
    ).all()
    return OkEnvelope(data=[PaymentOut.model_validate(p) for p in rows])


# ============== Mock topup (giữ cho backward compat, chưa tích hợp SePay) ==============

@router.post("/topup", response_model=OkEnvelope[Any])
def topup(
    payload: dict,  # {amount_credits: int, amount_vnd?: int}
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> OkEnvelope[Any]:
    """Mock credit top-up (legacy endpoint — chưa tích hợp SePay)."""
    raise HTTPException(
        _status.HTTP_501_NOT_IMPLEMENTED,
        detail="Credit top-up via SePay chưa được triển khai trong MVP. Dùng /payments/upgrade.",
    )