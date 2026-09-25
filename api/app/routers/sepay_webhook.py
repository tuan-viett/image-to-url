"""SePay webhook endpoint.

POST /api/v1/webhooks/sepay

3 phương thức auth SePay hỗ trợ (chọn trong .env / bảng configs):

    1. API Key     Authorization: Apikey YOUR_API_KEY         (đơn giản)
    2. HMAC        X-SePay-Signature: sha256=<hex>            (khuyến nghị)
                   X-SePay-Timestamp:  <unix_ts>
    3. OAuth 2.0   Authorization: Bearer <access_token>      (production)

Backend chấp nhận 1 trong 3. Mỗi method độc lập (nếu cấu hình → bật, không thì skip).

Body: JSON payload theo docs SePay. Quan trọng nhất:
    {
        "id": 12345,
        "gateway": "MBBank",
        "transactionDate": "2026-09-24T10:00:00Z",
        "accountNumber": "0123456789",
        "code": "IMGU AB12CD",
        "content": "IMGU AB12CD thanh toan",
        "transferType": "in",        // in | out
        "transferAmount": 100000,
        "referenceCode": "...",
        ...
    }

Luồng xử lý:
    1. Đọc raw body + verify auth (services/sepay).
    2. Parse JSON, chỉ xử lý ``transferType == "in"``.
    3. Tìm Payment theo ``code`` (UNIQUE) + status=PENDING + chưa hết hạn.
    4. UPDATE có điều kiện ``WHERE status=PENDING`` để chống double-spend
       khi SePay retry song song.
    5. Nếu khớp → grant credits / upgrade plan + đánh dấu STATUS_COMPLETED, paid_at.

Trả về ``{"success": true}`` cho cả khi idempotent (đã xử lý) để SePay không retry.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status as _status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.upload_credit import UploadCreditTransaction
from app.models.user import User
from app.services.credit_service import grant_credits
from app.services.sepay import (
    resolve_webhook_api_key,
    resolve_webhook_secret,
    verify_api_key,
    verify_webhook,
)

logger = logging.getLogger("imageurl.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _extract_code(content: str, fallback_code: str) -> Optional[str]:
    """Lấy phần ``IMGUAB12CD`` từ content ngân hàng.

    SePay đôi khi trả về ``content`` có thêm tiếng Việt đính kèm hoặc ký tự lạ
    (vd: ``"chuyen tien IMGUAB12CD cho anh"``). Tìm cụm ``IMGU`` + 8 ký tự
    alphanumeric đứng liền nhau; nếu không thấy thì dùng ``code`` field.
    Mã dính liền (không dấu cách giữa prefix và code) theo format hiện tại.
    """
    if not content:
        return None
    m = re.search(r"IMGU[A-Z0-9]{4,16}", content.upper())
    if m:
        return m.group(0)
    return fallback_code.strip().upper() if fallback_code else None


@router.post("/sepay")
async def sepay_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {"success": False, "message": "empty body"}

    # === Auth: thử tuần tự từng method. Chỉ cần 1 cái pass. ===
    auth = request.headers.get("Authorization")
    sig = request.headers.get("X-SePay-Signature")
    ts = request.headers.get("X-SePay-Timestamp")

    api_key = resolve_webhook_api_key(db)
    secret = resolve_webhook_secret(db)

    auth_ok = False
    auth_reason = ""

    # 1. API Key (nếu cấu hình)
    if api_key:
        ok, reason = verify_api_key(auth_header=auth, expected_key=api_key)
        if ok:
            auth_ok = True
        else:
            auth_reason = f"api_key: {reason}"

    # 2. HMAC (nếu cấu hình và API Key chưa pass)
    if not auth_ok and secret:
        ok, reason = verify_webhook(
            raw_body=raw, signature_header=sig, timestamp_header=ts, secret=secret,
        )
        if ok:
            auth_ok = True
        elif auth_reason:
            auth_reason += f"; hmac: {reason}"
        else:
            auth_reason = f"hmac: {reason}"

    # 3. Cả 2 fail hoặc không cấu hình → reject
    if not auth_ok:
        if not api_key and not secret:
            auth_reason = "no webhook auth configured (set sepay.api_key or sepay.webhook_secret in configs table)"
        logger.warning("SePay webhook rejected: %s", auth_reason)
        raise HTTPException(_status.HTTP_401_UNAUTHORIZED, detail=auth_reason)

    # Parse JSON
    try:
        data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(_status.HTTP_400_BAD_REQUEST, detail="invalid JSON")

    if data.get("transferType") != "in":
        # Outbound tx hoặc noise → ignore, vẫn trả 200 để SePay không retry.
        return {"success": True, "ignored": "not inbound"}

    sepay_id = data.get("id")
    code_raw = (data.get("code") or "").strip()
    content = (data.get("content") or "").strip()
    amount_received_vnd = int(data.get("transferAmount") or 0)
    account_received = (data.get("accountNumber") or "").strip()

    code_match = _extract_code(content, code_raw)
    if not code_match:
        logger.info("SePay webhook ignored: no code match (code=%r content=%r)", code_raw, content)
        return {"success": True, "ignored": "no matching code"}

    # Tìm Payment theo code (UNIQUE index)
    payment = db.scalar(select(Payment).where(Payment.code == code_match))
    if not payment:
        logger.info("SePay webhook: no payment found for code=%s", code_match)
        return {"success": True, "ignored": "unknown code"}

    # Race-safe: chỉ xử lý khi còn pending + chưa hết hạn + đúng số tiền.
    if payment.status != Payment.STATUS_PENDING:
        logger.info("SePay webhook: payment %s already status=%s", payment.id, payment.status)
        return {"success": True, "ignored": "already processed"}

    if payment.expires_at and payment.expires_at < datetime.utcnow():
        logger.info("SePay webhook: payment %s expired", payment.id)
        return {"success": True, "ignored": "expired"}

    # payment.amount lưu theo xu (1 VND = 100 xu); webhook trả VND → đổi về xu để so sánh.
    amount_received_xu = amount_received_vnd * 100
    if amount_received_xu < int(payment.amount):
        logger.warning(
            "SePay webhook: payment %s amount mismatch (paid_vnd=%s required_xu=%s)",
            payment.id, amount_received_vnd, payment.amount,
        )
        return {"success": True, "ignored": "amount too low"}

    # OPTIONAL check account_number snapshot (cảnh báo, không reject vì SePay đôi khi đổi tài khoản)
    if payment.sepay_account_number and account_received and payment.sepay_account_number != account_received:
        logger.warning(
            "SePay webhook: account mismatch payment %s (expected=%s got=%s)",
            payment.id, payment.sepay_account_number, account_received,
        )

    # === Apply business logic ===
    user = db.get(User, payment.user_id)
    if not user:
        logger.error("SePay webhook: payment %s references missing user_id=%s", payment.id, payment.user_id)
        return {"success": True, "ignored": "user missing"}

    if payment.type == Payment.TYPE_PLAN_UPGRADE:
        if payment.plan_id is None:
            logger.error("SePay webhook: payment %s missing plan_id", payment.id)
            return {"success": True, "ignored": "plan_id missing"}

        plan = db.get(Plan, payment.plan_id)
        if not plan:
            logger.error("SePay webhook: payment %s missing plan %s", payment.id, payment.plan_id)
            return {"success": True, "ignored": "plan missing"}

        current_plan = db.get(Plan, user.plan_id) if user.plan_id else None
        is_downgrade = current_plan and plan.sort_order < current_plan.sort_order
        if is_downgrade:
            # API đã block, không tới đây. Log để debug nếu xảy ra.
            logger.warning("SePay webhook: payment %s — downgrade attempt (sort_order %s→%s)",
                           payment.id, current_plan.sort_order, plan.sort_order)
        else:
            # Upgrade (sort_order cao hơn) → đổi plan_id + grant credits.
            # Renewal (sort_order bằng) → KHÔNG đổi plan_id nhưng VẪN grant credits
            # vì user trả tiền để mua thêm lượt upload.
            if current_plan and plan.sort_order > current_plan.sort_order:
                user.plan_id = plan.id
            grant_credits(
                db,
                user_id=user.id,
                amount=plan.initial_uploads,
                type_=UploadCreditTransaction.TYPE_PLAN_GRANT,
                reference_type="plan",
                reference_id=plan.id,
            )

    elif payment.type == Payment.TYPE_CREDIT_TOPUP:
        if not payment.credits:
            logger.error("SePay webhook: payment %s missing credits", payment.id)
            return {"success": True, "ignored": "credits missing"}
        grant_credits(
            db,
            user_id=user.id,
            amount=payment.credits,
            type_=UploadCreditTransaction.TYPE_TOPUP,
            reference_type="payment",
            reference_id=payment.id,
        )

    # === Đóng đơn ===
    payment.status = Payment.STATUS_COMPLETED
    payment.paid_at = datetime.utcnow()
    payment.sepay_id = sepay_id
    payment.sepay_content_received = content[:255] if content else None
    payment.provider_transaction_id = str(sepay_id) if sepay_id is not None else None

    db.commit()
    logger.info(
        "SePay webhook: payment %s completed (user=%s amount_vnd=%s)",
        payment.id, user.id, amount_received_vnd,
    )
    return {"success": True}