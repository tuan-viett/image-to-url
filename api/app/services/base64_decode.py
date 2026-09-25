"""Parse Base64 input (raw or data-URI) into bytes."""
from __future__ import annotations

import base64
import binascii
import re
from typing import Tuple

from app.errors import AppError, ErrorCode


_DATA_URI_RE = re.compile(r"^data:(?P<mime>[\w./+-]+);base64,(?P<data>.+)$", re.DOTALL)


def parse_base64_image(payload: str) -> Tuple[bytes, str | None]:
    """Return (decoded_bytes, mime_or_None).

    Accepts both:
      data:image/png;base64,iVBOR...
      iVBORw0KGgo...
    """
    if payload is None:
        raise AppError(ErrorCode.INVALID_BASE64, "Empty Base64 payload")

    s = payload.strip()
    if not s:
        raise AppError(ErrorCode.INVALID_BASE64, "Empty Base64 payload")

    mime: str | None = None
    body = s
    m = _DATA_URI_RE.match(s)
    if m:
        mime = m.group("mime").strip().lower()
        body = m.group("data").strip()
        # Reject obvious non-image data URIs early. (Real MIME detection happens
        # by magic bytes in image_processor.)
        if mime and not mime.startswith("image/"):
            raise AppError(ErrorCode.UNSUPPORTED_FORMAT, f"Data URI MIME not an image: {mime}")
        if mime and mime == "image/svg+xml":
            raise AppError(ErrorCode.UNSUPPORTED_FORMAT, "SVG is not supported (security)")

    # Allow whitespace inside the Base64 string.
    body_clean = re.sub(r"\s+", "", body)
    if len(body_clean) == 0:
        raise AppError(ErrorCode.INVALID_BASE64, "Empty Base64 payload")
    if len(body_clean) % 4 != 0:
        # Add padding
        body_clean = body_clean + "=" * (-len(body_clean) % 4)

    try:
        decoded = base64.b64decode(body_clean, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise AppError(ErrorCode.INVALID_BASE64, "Base64 decoding failed", details={"reason": str(exc)}) from exc

    return decoded, mime