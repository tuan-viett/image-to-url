"""API key creation, lookup and verification.

We store only bcrypt(key) and the prefix. The plaintext secret is returned to
the user exactly once at creation time (PLAN §3.6).

For lookup by raw token, we identify candidates by the unique `key_prefix`,
then bcrypt-verify the candidate against `key_hash`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api_key import ApiKey
from app.security import verify_password
from app.services.key_generator import generate_api_key


def _parse_env_from_secret(secret: str) -> int:
    if secret.startswith("sk_live_"):
        return ApiKey.ENV_LIVE
    if secret.startswith("sk_test_"):
        return ApiKey.ENV_TEST
    return ApiKey.ENV_LIVE  # default


def create_api_key(
    db: Session,
    *,
    user_id: int,
    name: str,
    environment: int,
) -> tuple[ApiKey, str]:
    """Create a new API key. Returns (db_record, plaintext_secret)."""
    if environment not in (ApiKey.ENV_LIVE, ApiKey.ENV_TEST):
        environment = ApiKey.ENV_LIVE

    full, prefix, _random = generate_api_key(environment)
    # We hash the FULL secret (including prefix) so a leaked DB row still
    # requires an attacker to brute-force a bcrypt-salted value.
    from app.security import hash_password

    record = ApiKey(
        user_id=user_id,
        name=name.strip()[:120] or "Untitled",
        key_prefix=prefix,
        key_hash=hash_password(full),
        environment=environment,
    )
    db.add(record)
    db.flush()
    return record, full


def verify_api_key(db: Session, raw_secret: str) -> Optional[ApiKey]:
    """Locate candidate by prefix, then bcrypt-verify. Returns None if no match."""
    if not raw_secret.startswith("sk_"):
        return None
    parts = raw_secret.split("_", 2)
    if len(parts) < 3:
        return None
    env_label = parts[1]
    prefix_tail = parts[2][:6]
    prefix = f"sk_{env_label}_{prefix_tail}"

    candidate = db.scalar(select(ApiKey).where(ApiKey.key_prefix == prefix))
    if not candidate:
        return None
    if not verify_password(raw_secret, candidate.key_hash):
        return None
    return candidate


def mark_used(db: Session, api_key: ApiKey) -> None:
    api_key.last_used_at = datetime.utcnow()