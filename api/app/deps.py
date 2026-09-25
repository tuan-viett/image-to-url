"""Common FastAPI dependencies."""
from typing import Optional

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError, ErrorCode
from app.security import decode_access_token
from app.models.user import User
from app.models.api_key import ApiKey
from app.services.api_key_service import verify_api_key


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(ErrorCode.UNAUTHORIZED, "Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload:
        raise AppError(ErrorCode.UNAUTHORIZED, "Invalid or expired token")
    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise AppError(ErrorCode.UNAUTHORIZED, "Invalid token payload")
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        raise AppError(ErrorCode.UNAUTHORIZED, "Invalid token subject")

    user = db.get(User, user_id)
    if not user:
        raise AppError(ErrorCode.UNAUTHORIZED, "User not found")
    return user


def get_optional_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not authorization:
        return None
    try:
        return get_current_user(authorization=authorization, db=db)
    except AppError:
        return None


def get_current_api_key(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Authenticate via API key. Supports both `Bearer sk_xxx` and direct `sk_xxx`."""
    if not authorization:
        raise AppError(ErrorCode.UNAUTHORIZED, "Missing Authorization header")
    raw = authorization.strip()
    if raw.lower().startswith("bearer "):
        raw = raw.split(" ", 1)[1].strip()
    if not raw.startswith("sk_"):
        raise AppError(ErrorCode.INVALID_API_KEY, "API key must start with sk_")
    api_key = verify_api_key(db, raw)
    if not api_key:
        raise AppError(ErrorCode.INVALID_API_KEY, "Invalid API key")
    if api_key.revoked_at is not None:
        raise AppError(ErrorCode.API_KEY_REVOKED, "API key has been revoked")
    return api_key


def get_current_user_or_api_key(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[Optional[User], Optional[ApiKey]]:
    """Resolve either a JWT user or an API key (and its owner)."""
    auth = request.headers.get("authorization")
    if not auth:
        raise AppError(ErrorCode.UNAUTHORIZED, "Authentication required")
    raw = auth.strip()
    if raw.lower().startswith("bearer "):
        raw = raw.split(" ", 1)[1].strip()
    if raw.startswith("sk_"):
        api_key = verify_api_key(db, raw)
        if not api_key:
            raise AppError(ErrorCode.INVALID_API_KEY, "Invalid API key")
        if api_key.revoked_at is not None:
            raise AppError(ErrorCode.API_KEY_REVOKED, "API key has been revoked")
        user = db.get(User, api_key.user_id)
        return user, api_key
    # Treat as JWT
    try:
        user = get_current_user(authorization=auth, db=db)
        return user, None
    except AppError:
        raise