"""Cryptographically-secure generators for storage keys and API secrets."""
from __future__ import annotations

import secrets
import string


def generate_storage_key() -> str:
    """~22-char URL-safe random string. Used as the disk filename (sans ext)."""
    return secrets.token_urlsafe(16)


def generate_api_key(environment: int) -> tuple[str, str, str]:
    """Generate a (full_secret, key_prefix, key_hash_components).

    Returns:
        full_secret   - the secret the client must save (returned ONCE).
        key_prefix    - the prefix we store in plain text (e.g. 'sk_live_aB12cD3').
        secret_part   - the random secret part (used to bcrypt the full secret).
    """
    env_label = "live" if environment == 1 else "test"
    random_part = secrets.token_urlsafe(24)
    full = f"sk_{env_label}_{random_part}"
    # prefix keeps first 4 chars of random_part so users can distinguish keys visually
    prefix = f"sk_{env_label}_{random_part[:6]}"
    return full, prefix, random_part