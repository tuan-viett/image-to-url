"""Credit accounting with row-level locking.

`consume_credit` uses SELECT ... FOR UPDATE inside a transaction so concurrent
uploads can never oversubscribe credits (PLAN §8 important note).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, ErrorCode
from app.models.upload_credit import UploadCreditTransaction
from app.models.user import User


def consume_credit(
    db: Session,
    *,
    user_id: int,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
) -> int:
    """Atomically decrement user's upload credits by 1.

    Returns the new balance_after. Raises QUOTA_EXCEEDED if the balance is 0.
    Must be called inside the same transaction that creates the Image row.
    """
    user = db.execute(
        select(User).where(User.id == user_id).with_for_update()
    ).scalar_one_or_none()
    if not user:
        raise AppError(ErrorCode.UNAUTHORIZED, "User not found")
    if user.upload_credits <= 0:
        raise AppError(
            ErrorCode.QUOTA_EXCEEDED,
            "No upload credits remaining. Please top up or upgrade your plan.",
            details={"upload_credits": 0},
        )

    user.upload_credits -= 1
    db.add(
        UploadCreditTransaction(
            user_id=user_id,
            type=UploadCreditTransaction.TYPE_UPLOAD,
            amount=-1,
            balance_after=user.upload_credits,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    )
    return user.upload_credits


def grant_credits(
    db: Session,
    *,
    user_id: int,
    amount: int,
    type_: int,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
) -> int:
    """Atomically add credits (PLAN_GRANT / TOPUP / ADMIN_ADJUSTMENT / REFUND)."""
    user = db.execute(
        select(User).where(User.id == user_id).with_for_update()
    ).scalar_one_or_none()
    if not user:
        raise AppError(ErrorCode.UNAUTHORIZED, "User not found")
    if amount <= 0:
        raise ValueError("grant_credits requires amount > 0")
    user.upload_credits += amount
    db.add(
        UploadCreditTransaction(
            user_id=user_id,
            type=type_,
            amount=amount,
            balance_after=user.upload_credits,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    )
    return user.upload_credits