"""Authenticated image upload, list, get, delete."""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError, ErrorCode
from app.models.api_key import ApiKey
from app.models.image import Image
from app.models.user import User
from app.deps import get_current_user, get_current_user_or_api_key
from app.schemas.image import Base64ImageIn, ImageOut, UploadOut
from app.schemas.common import OkEnvelope, Pagination, PaginationEnvelope
from app.services.base64_decode import parse_base64_image
from app.services.upload_service import perform_upload


router = APIRouter(prefix="/images", tags=["images"])


def _to_out(img: Image) -> ImageOut:
    return ImageOut.model_validate(img)


@router.post("", response_model=OkEnvelope[UploadOut])
async def upload(
    request: Request,
    db: Session = Depends(get_db),
    file: Optional[UploadFile] = File(default=None),
    image: Optional[str] = Form(default=None),
    filename: Optional[str] = Form(default=None),
    user_key=Depends(get_current_user_or_api_key),
) -> OkEnvelope[UploadOut]:
    user: Optional[User]
    api_key: Optional[ApiKey]
    user, api_key = user_key
    assert user is not None  # the dep already raises otherwise

    raw: bytes | None = None
    orig_name = ""
    source = Image.SOURCE_BASE64  # default; overridden if a file is uploaded
    if file is not None:
        raw = file.file.read()
        orig_name = file.filename or "upload"
        source = Image.SOURCE_API if api_key else Image.SOURCE_WEB_UPLOAD
    elif image:
        decoded, mime = parse_base64_image(image)
        raw = decoded
        orig_name = (filename or "").strip() or (mime or "base64")
    else:
        # Fall back to JSON body for callers that prefer JSON over multipart
        # (matches what the dashboard "Documentation" tab documents).
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
        source=source,
        user=user,
        api_key_id=api_key.id if api_key else None,
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


@router.get("", response_model=PaginationEnvelope[ImageOut])
def list_images(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_key=Depends(get_current_user_or_api_key),
) -> PaginationEnvelope[ImageOut]:
    user, _ = user_key
    assert user is not None
    total = db.execute(
        select(Image.id).where(Image.user_id == user.id, Image.deleted_at.is_(None))
    ).all()
    total_count = len(total)
    rows = db.scalars(
        select(Image)
        .where(Image.user_id == user.id, Image.deleted_at.is_(None))
        .order_by(Image.created.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return PaginationEnvelope(
        data=[_to_out(r) for r in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total_count),
    )


@router.get("/{image_id}", response_model=OkEnvelope[ImageOut])
def get_image(
    image_id: int,
    db: Session = Depends(get_db),
    user_key=Depends(get_current_user_or_api_key),
) -> OkEnvelope[ImageOut]:
    user, _ = user_key
    img = db.scalar(select(Image).where(Image.id == image_id))
    if not img or img.deleted_at is not None:
        raise AppError(ErrorCode.IMAGE_NOT_FOUND, "Image not found")
    if img.user_id != user.id:
        raise AppError(ErrorCode.IMAGE_NOT_FOUND, "Image not found")  # don't leak existence
    return OkEnvelope(data=_to_out(img))


@router.delete("/{image_id}", response_model=OkEnvelope[dict])
def delete_image(
    image_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
) -> OkEnvelope[dict]:
    img = db.scalar(select(Image).where(Image.id == image_id).with_for_update())
    if not img or img.deleted_at is not None:
        raise AppError(ErrorCode.IMAGE_NOT_FOUND, "Image not found")
    if img.user_id != current.id:
        raise AppError(ErrorCode.IMAGE_NOT_FOUND, "Image not found")
    from datetime import datetime
    img.deleted_at = datetime.utcnow()
    from app.models.usage_event import UsageEvent
    db.add(
        UsageEvent(
            user_id=current.id,
            event_type=UsageEvent.TYPE_DELETE,
            bytes=img.size_bytes,
            metadata_json={"image_id": img.id},
        )
    )
    db.commit()
    return OkEnvelope(data={"id": img.id, "deleted": True})