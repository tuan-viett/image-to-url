"""Auth: register, login."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.errors import AppError, ErrorCode
from app.models.plan import Plan
from app.models.user import User
from app.schemas.auth import AuthOut, LoginIn, RegisterIn, TokenOut, UserOut
from app.schemas.common import OkEnvelope
from app.security import create_access_token, hash_password, verify_password
from app.services.credit_service import grant_credits
from app.models.upload_credit import UploadCreditTransaction

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        plan_id=user.plan_id,
        upload_credits=user.upload_credits,
        plan_initial_uploads=user.plan.initial_uploads,
        plan_name=user.plan.name,
        plan_sort_order=user.plan.sort_order,
        plan_retention_days=user.plan.retention_days,
        plan_image_quality=user.plan.image_quality,
        created=user.created,
        modified=user.modified,
    )


@router.post("/register", response_model=OkEnvelope[AuthOut])
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> OkEnvelope[AuthOut]:
    # Free plan = the plan with sort_order=0 and price=0
    free_plan = db.scalar(select(Plan).where(Plan.price == 0).order_by(Plan.sort_order.asc()))
    if free_plan is None:
        raise AppError(ErrorCode.INTERNAL_ERROR, "No Free plan configured")

    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise AppError(ErrorCode.EMAIL_TAKEN, "Email is already registered")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        name=payload.name.strip(),
        plan_id=free_plan.id,
        upload_credits=free_plan.initial_uploads,
    )
    db.add(user)
    db.flush()
    # Audit grant
    if free_plan.initial_uploads > 0:
        db.add(
            UploadCreditTransaction(
                user_id=user.id,
                type=UploadCreditTransaction.TYPE_PLAN_GRANT,
                amount=free_plan.initial_uploads,
                balance_after=free_plan.initial_uploads,
                reference_type="plan",
                reference_id=free_plan.id,
            )
        )
    db.commit()
    db.refresh(user)

    token = create_access_token(str(user.id))
    return OkEnvelope(
        data=AuthOut(
            user=_user_to_out(user),
            access_token=token,
            expires_in=get_settings().jwt_access_ttl_minutes * 60,
        )
    )


@router.post("/login", response_model=OkEnvelope[AuthOut])
def login(payload: LoginIn, db: Session = Depends(get_db)) -> OkEnvelope[AuthOut]:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise AppError(ErrorCode.BAD_CREDENTIALS, "Email or password is incorrect")
    token = create_access_token(str(user.id))
    return OkEnvelope(
        data=AuthOut(
            user=_user_to_out(user),
            access_token=token,
            expires_in=get_settings().jwt_access_ttl_minutes * 60,
        )
    )


@router.get("/me", response_model=OkEnvelope[UserOut])
def me(current: User = Depends(get_current_user)) -> OkEnvelope[UserOut]:
    return OkEnvelope(data=_user_to_out(current))