"""Rate limiting via slowapi.

For MVP we use the default in-memory storage; sufficient for single-instance
deploy. Redis-backed storage can be added later without touching this module.
"""
from fastapi import Request
from slowapi import Limiter

from app.config import get_settings


def _client_ip(request: Request) -> str:
    # nginx (the only expected proxy in this stack) sets X-Forwarded-For.
    # We take the leftmost (original client) entry.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


_settings = get_settings()
limiter = Limiter(key_func=_client_ip, default_limits=[])