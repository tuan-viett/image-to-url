"""Public image serving — no auth required.

Storage path is /i/{key[:2]}/{key[2:4]}/{storage_key}.{ext}
Validates the storage_key regex strictly (PLAN §14 + security notes).

Note: nginx serves these directly from the shared volume in production;
this FastAPI route is the fallback when running the API standalone.
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.storage import KEY_RE, get_storage


router = APIRouter(prefix="/i", tags=["public"])


@router.get("/{shard1}/{shard2}/{storage_key}.{ext}")
def serve_image(shard1: str, shard2: str, storage_key: str, ext: str):
    if shard1 != storage_key[:2] or shard2 != storage_key[2:4]:
        raise HTTPException(status_code=404, detail="Not found")
    if not KEY_RE.match(storage_key):
        raise HTTPException(status_code=404, detail="Not found")
    ext = ext.lower()
    if not re.match(r"^[a-z0-9]{1,10}$", ext):
        raise HTTPException(status_code=404, detail="Not found")

    storage = get_storage()
    try:
        path = Path(storage._path(storage_key, ext))  # type: ignore[attr-defined]
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")

    mime = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")

    return FileResponse(
        path,
        media_type=mime,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )