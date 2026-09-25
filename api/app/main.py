"""ImageURL FastAPI app entrypoint.

Public surface (under /api/v1):
  - auth/, users, images, anonymous, api-keys, usage, plans, payments
Public serving (no auth, separate top-level path):
  - /i/{storage_key}.{ext}
Static files (mounted last; nginx in production serves them):
  - /static -> web app
  (web is served by nginx in this stack; static mount is here for dev only)
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.errors import AppError, ErrorCode, error_payload
from app.rate_limit import limiter
from app.routers import (
    api_keys,
    auth,
    images,
    anonymous,
    payments,
    public_serve,
    sepay_webhook,
    usage as usage_router,
)


settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)

app = FastAPI(
    title="ImageURL API",
    version="0.1.0",
    description="Image infrastructure SaaS — turn images into public URLs.",
)

app.state.limiter = limiter

# CORS — whitelist origins from .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception: rate-limit
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Exception: AppError (consistent error envelope)
@app.exception_handler(AppError)
async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    payload = error_payload(exc.code, exc.message, exc.details)
    return JSONResponse(status_code=exc.status_code, content=payload)


# Routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(images.router, prefix="/api/v1")
app.include_router(anonymous.router, prefix="/api/v1")
app.include_router(api_keys.router, prefix="/api/v1")
app.include_router(usage_router.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(sepay_webhook.router, prefix="/api/v1")
app.include_router(public_serve.router)


@app.get("/healthz", tags=["health"])
def healthz() -> dict:
    return {"status": "ok"}


# Static (optional; nginx serves these in production).
STATIC_DIR = Path(__file__).resolve().parent.parent / "web"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


@app.get("/", include_in_schema=False)
def root_index():
    """If static files are not mounted (e.g. when running uvicorn alone),
    redirect to /static/index.html via the mount; otherwise return 404."""
    if STATIC_DIR.exists():
        return RedirectResponse(url="/index.html")
    return JSONResponse({"error": "web/ not built"}, status_code=500)