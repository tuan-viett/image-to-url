"""Anonymous upload (no auth, IP rate-limited)."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import AppError, ErrorCode
from app.models.image import Image
from app.models.usage_event import UsageEvent
from app.rate_limit import limiter
from app.schemas.image import UploadOut
from app.schemas.common import OkEnvelope
from app.services.base64_decode import parse_base64_image
from app.services.upload_service import perform_upload


router = APIRouter(prefix="/anonymous", tags=["anonymous"])


@router.post(
    "/images",
    response_model=OkEnvelope[UploadOut],
    summary="Upload an image anonymously (IP rate limited)",
)
@limiter.limit(lambda: f"{get_settings().anon_daily_limit}/day")
async def anonymous_upload(
    request: Request,
    db: Session = Depends(get_db),
    file: Optional[UploadFile] = File(default=None),
    image: Optional[str] = Form(default=None),
    filename: Optional[str] = Form(default=None),
) -> OkEnvelope[UploadOut]:
    raw: bytes | None = None
    orig_name = ""
    if file is not None:
        # We accept an in-memory read; size cap is checked in validate_and_process.
        raw = file.file.read()
        orig_name = file.filename or "upload"
    elif image:
        decoded, mime = parse_base64_image(image)
        raw = decoded
        orig_name = (filename or "").strip() or (mime or "base64")
    else:
        # JSON body fallback (matches the dashboard Documentation example)
        try:
            body = await request.json()
        except Exception:
            body = None
        if body and isinstance(body, dict) and body.get("image"):
            decoded, mime = parse_base64_image(body["image"])
            raw = decoded
            orig_name = (body.get("filename") or "").strip() or (mime or "base64")
        else:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Either `file` or `image` must be provided")

    img, processed = perform_upload(
        db,
        raw=raw,
        original_filename=orig_name,
        source=Image.SOURCE_ANONYMOUS_UPLOAD,
        user=None,
        api_key_id=None,
    )
    return OkEnvelope(
        data=UploadOut(
            id=img.id,
            url=img.public_url,
            mime_type=img.mime_type,
            size=img.size_bytes,
            created_at=img.created,
        )
    )