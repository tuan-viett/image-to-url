"""Image validation, format detection and processing.

Whitelisted formats (PLAN §3.1): JPEG, PNG, WebP, GIF.
SVG is rejected outright at MVP — it can carry active content (XSS / JS).
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Tuple

from PIL import Image as PILImage
from PIL.Image import Image

from app.errors import AppError, ErrorCode


SUPPORTED_FORMATS: dict[str, tuple[str, str]] = {
    # Pillow format name -> (mime, file extension)
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "GIF": ("image/gif", "gif"),
    "WEBP": ("image/webp", "webp"),
}

# Magic-byte signatures for the formats we accept.
_MAGIC = {
    "JPEG": (b"\xff\xd8\xff",),
    "PNG": (b"\x89PNG\r\n\x1a\n",),
    "GIF": (b"GIF87a", b"GIF89a"),
    "WEBP": (b"RIFF",),  # followed by 4 bytes size + "WEBP" at offset 8
}

_WEBP_FULL = b"WEBP"


@dataclass
class ProcessedImage:
    data: bytes
    mime_type: str
    extension: str
    width: int
    height: int
    sha256_hex: str
    image_quality: int  # 0=optimized, 1=original


def _detect_format_from_magic(buf: bytes) -> str | None:
    if buf.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if buf.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if buf.startswith(b"GIF87a") or buf.startswith(b"GIF89a"):
        return "GIF"
    if buf.startswith(b"RIFF") and len(buf) >= 12 and buf[8:12] == _WEBP_FULL:
        return "WEBP"
    return None


def _read_magic(raw: bytes, n: int = 16) -> bytes:
    return raw[:n]


def validate_and_process(
    raw: bytes,
    *,
    max_pixels: int,
    image_quality: int,
    max_bytes: int,
) -> ProcessedImage:
    """Validate magic bytes, decode, run pixel-bomb + EXIF strip checks.

    Returns a fully-processed image ready for storage.
    Raises AppError with the appropriate code on any failure.
    """
    if len(raw) == 0:
        raise AppError(ErrorCode.INVALID_IMAGE, "Empty payload")
    if len(raw) > max_bytes:
        raise AppError(
            ErrorCode.FILE_TOO_LARGE,
            f"Image exceeds the {max_bytes // (1024 * 1024)} MB limit for this upload.",
            details={"max_bytes": max_bytes},
        )

    fmt_name = _detect_format_from_magic(_read_magic(raw))
    if fmt_name is None:
        raise AppError(
            ErrorCode.UNSUPPORTED_FORMAT,
            "Unsupported image format. Allowed: JPEG, PNG, WebP, GIF.",
        )
    if fmt_name not in SUPPORTED_FORMATS:
        raise AppError(ErrorCode.UNSUPPORTED_FORMAT, f"Format {fmt_name} is not supported")

    # Decode with Pillow to catch malformed/truncated images.
    try:
        pil = PILImage.open(io.BytesIO(raw))
        pil.verify()  # structural check (raises if not a real image)
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCode.INVALID_IMAGE, "Cannot decode image", details={"reason": str(exc)}) from exc

    # Reload (verify() invalidates the instance) to extract dimensions.
    try:
        pil = PILImage.open(io.BytesIO(raw))
        pil.load()
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCode.INVALID_IMAGE, "Cannot decode image", details={"reason": str(exc)}) from exc

    width, height = pil.size
    if width <= 0 or height <= 0:
        raise AppError(ErrorCode.INVALID_IMAGE, "Image has zero dimensions")
    if width * height > max_pixels:
        raise AppError(
            ErrorCode.INVALID_IMAGE,
            "Image dimensions too large (pixel bomb protection)",
            details={"pixels": width * height, "max_pixels": max_pixels},
        )

    # Strip EXIF / metadata by re-saving. For original quality we still strip
    # sensitive GPS data — the security trade-off favors privacy.
    out_bytes = _re_encode_stripped(pil, fmt_name)

    # Re-validate size after re-encode (could shrink a lot for PNG).
    if len(out_bytes) > max_bytes:
        raise AppError(
            ErrorCode.FILE_TOO_LARGE,
            "Processed image exceeds size limit.",
            details={"bytes": len(out_bytes), "max_bytes": max_bytes},
        )

    sha = hashlib.sha256(out_bytes).hexdigest()
    mime, ext = SUPPORTED_FORMATS[fmt_name]
    return ProcessedImage(
        data=out_bytes,
        mime_type=mime,
        extension=ext,
        width=pil.size[0],
        height=pil.size[1],
        sha256_hex=sha,
        image_quality=image_quality,
    )


def _re_encode_stripped(pil: Image, fmt_name: str) -> bytes:
    """Re-encode stripped image into the bytes we actually persist."""
    buf = io.BytesIO()
    fmt = fmt_name
    if fmt == "JPEG":
        if pil.mode != "RGB":
            pil = pil.convert("RGB")
        pil.save(buf, format="JPEG", quality=85, optimize=True)
    elif fmt == "PNG":
        # Pillow's optimize does a decent job for PNG.
        pil.save(buf, format="PNG", optimize=True)
    elif fmt == "WEBP":
        pil.save(buf, format="WEBP", quality=85, method=6)
    elif fmt == "GIF":
        pil.save(buf, format="GIF")
    else:  # pragma: no cover - validated upstream
        raise AppError(ErrorCode.UNSUPPORTED_FORMAT, fmt_name)
    return buf.getvalue()


def extension_for_mime(mime: str) -> str:
    for _fmt, (m, ext) in SUPPORTED_FORMATS.items():
        if m == mime:
            return ext
    return "img"