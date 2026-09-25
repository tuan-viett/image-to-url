"""API key management."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.errors import AppError, ErrorCode
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import ApiKeyCreateIn, ApiKeyOut, ApiKeyWithSecretOut
from app.schemas.common import OkEnvelope, Pagination, PaginationEnvelope
from app.services.api_key_service import create_api_key


router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("", response_model=OkEnvelope[ApiKeyWithSecretOut])
def create(
    payload: ApiKeyCreateIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> OkEnvelope[ApiKeyWithSecretOut]:
    record, secret = create_api_key(
        db,
        user_id=current.id,
        name=payload.name,
        environment=payload.environment,
    )
    db.commit()
    db.refresh(record)
    out = ApiKeyWithSecretOut(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        environment=record.environment,
        last_used_at=record.last_used_at,
        created=record.created,
        revoked_at=record.revoked_at,
        secret=secret,
    )
    return OkEnvelope(data=out)


@router.get("", response_model=PaginationEnvelope[ApiKeyOut])
def list_keys(
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 20,
    current: User = Depends(get_current_user),
) -> PaginationEnvelope[ApiKeyOut]:
    base_q = select(ApiKey).where(ApiKey.user_id == current.id)
    total = len(db.execute(base_q).all())
    rows = db.scalars(
        base_q.order_by(ApiKey.created.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PaginationEnvelope(
        data=[ApiKeyOut.model_validate(r) for r in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.delete("/{key_id}", response_model=OkEnvelope[dict])
def revoke(
    key_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> OkEnvelope[dict]:
    record = db.scalar(select(ApiKey).where(ApiKey.id == key_id).with_for_update())
    if not record or record.user_id != current.id:
        raise AppError(ErrorCode.IMAGE_NOT_FOUND, "API key not found")
    if record.revoked_at is None:
        record.revoked_at = datetime.utcnow()
        db.commit()
    return OkEnvelope(data={"id": record.id, "revoked": True})