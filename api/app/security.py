"""Password hashing and JWT helpers."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
_settings = get_settings()


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(
    subject: str,
    extra: Optional[Dict[str, Any]] = None,
    ttl_minutes: Optional[int] = None,
) -> str:
    now = datetime.now(timezone.utc)
    exp_minutes = ttl_minutes if ttl_minutes is not None else _settings.jwt_access_ttl_minutes
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    except JWTError:
        return None