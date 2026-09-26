"""Wrapper cho external AI image generation provider.

Endpoint mặc định: ``POST https://router.auto-socials.com/v1/images/generations``
(OpenAI-compatible). Body::

    {
      "model": "ag/gemini-3.1-flash-image",
      "prompt": "A cute cat wearing a hat",
      "n": 1,
      "size": "1024x1024",
      "quality": "auto",
      "background": "auto",
      "image_detail": "auto",
      "output_format": "png"
    }

Response::

    {
      "created": 1234567890,
      "data": [{"b64_json": "iVBORw0KGgo..."}]
    }

``generate_image()`` raise ``AppError`` với code phù hợp nếu provider lỗi:
  - ``AI_TIMEOUT``        → HTTP 504
  - ``AI_CONTENT_BLOCKED`` → HTTP 400 (content policy violation)
  - ``AI_PROVIDER_ERROR`` → HTTP 502 (mọi lỗi còn lại)

API key được đọc qua ``Config`` table — caller (ai_service) truyền vào từ DB.
Hàm này KHÔNG đọc DB trực tiếp để giữ thuần I/O, dễ test.
"""
from __future__ import annotations

import base64
import binascii
import logging
from typing import Any, Optional

import httpx

from app.errors import AppError, ErrorCode

logger = logging.getLogger("imageurl.ai_provider")


# Default config — caller nên override từ DB.
DEFAULT_API_URL = "https://router.auto-socials.com/v1/images/generations"
DEFAULT_MODEL = "ag/gemini-3.1-flash-image"
DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_OUTPUT_BYTES = 25 * 1024 * 1024  # 25 MB — cap cho payload base64 (provider thường <10MB)


class AIProviderError(Exception):
    """Internal marker — sẽ được convert sang ``AppError`` ở layer trên."""


def _redact(value: Optional[str]) -> str:
    """Ẩn API key trong log — chỉ hiện 4 ký tự đầu + 4 ký tự cuối."""
    if not value:
        return "<empty>"
    if len(value) <= 12:
        return "***"
    return f"{value[:4]}...{value[-4:]} (len={len(value)})"


async def generate_image(
    *,
    api_url: str,
    api_key: str,
    prompt: str,
    model: Optional[str] = None,
    n: int = 1,
    size: Optional[str] = None,
    quality: Optional[str] = None,
    background: Optional[str] = None,
    image_detail: Optional[str] = None,
    output_format: str = "png",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[bytes]:
    """Gọi provider và trả về list of decoded image bytes.

    Raises ``AppError`` với error code phù hợp.
    Trả về list (length = ``n``) — caller chọn ảnh đầu tiên.
    """
    if not api_url:
        raise AppError(ErrorCode.AI_PROVIDER_ERROR, "AI provider URL not configured")
    if not api_key:
        raise AppError(ErrorCode.AI_PROVIDER_ERROR, "AI provider API key not configured")

    payload: dict[str, Any] = {
        "prompt": prompt,
        "n": n,
        "model": model or DEFAULT_MODEL,
        "output_format": output_format,
    }
    # Optional fields — chỉ gửi khi client/provider đã set
    for k, v in (
        ("size", size),
        ("quality", quality),
        ("background", background),
        ("image_detail", image_detail),
    ):
        if v:
            payload[k] = v

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    logger.info(
        "AI gen request: url=%s model=%s n=%s prompt_len=%d api_key=%s",
        api_url, payload["model"], n, len(prompt), _redact(api_key),
    )

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(api_url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        logger.warning("AI provider timeout: %s", exc)
        raise AppError(
            ErrorCode.AI_TIMEOUT,
            f"AI provider did not respond within {timeout_seconds:.0f}s",
            details={"timeout_seconds": timeout_seconds},
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("AI provider network error: %s", exc)
        raise AppError(
            ErrorCode.AI_PROVIDER_ERROR,
            "AI provider unreachable",
            details={"reason": str(exc)[:200]},
        ) from exc

    # ---- Parse response ----
    if resp.status_code == 400:
        # Content policy hoặc invalid request
        body_text = resp.text[:500] if resp.text else ""
        is_content = "content_policy" in body_text.lower() or "safety" in body_text.lower()
        code = ErrorCode.AI_CONTENT_BLOCKED if is_content else ErrorCode.VALIDATION_ERROR
        logger.warning("AI provider rejected request (400): %s", body_text)
        raise AppError(
            code,
            "AI provider rejected the request (content policy or invalid input)",
            details={"provider_status": 400, "body": body_text},
        )

    if resp.status_code >= 400:
        logger.warning("AI provider error: status=%s body=%s", resp.status_code, resp.text[:500])
        raise AppError(
            ErrorCode.AI_PROVIDER_ERROR,
            f"AI provider returned status {resp.status_code}",
            details={"provider_status": resp.status_code, "body": resp.text[:500]},
        )

    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise AppError(
            ErrorCode.AI_PROVIDER_ERROR,
            "AI provider returned non-JSON response",
            details={"body": resp.text[:500], "reason": str(exc)},
        ) from exc

    items = data.get("data") or []
    if not isinstance(items, list) or len(items) == 0:
        raise AppError(
            ErrorCode.AI_PROVIDER_ERROR,
            "AI provider response missing `data` array",
            details={"keys": list(data.keys())},
        )

    out: list[bytes] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise AppError(
                ErrorCode.AI_PROVIDER_ERROR,
                f"AI provider data[{idx}] is not an object",
            )
        b64 = item.get("b64_json") or item.get("b64") or item.get("image_base64")
        if not b64:
            # Provider có thể trả URL thay vì base64 (chưa hỗ trợ trong MVP).
            url = item.get("url")
            raise AppError(
                ErrorCode.AI_PROVIDER_ERROR,
                "AI provider did not return b64_json (only URL is supported, not yet implemented)",
                details={"got_url": bool(url), "data_index": idx},
            )

        try:
            raw = base64.b64decode(b64, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise AppError(
                ErrorCode.AI_PROVIDER_ERROR,
                f"AI provider returned invalid base64 at data[{idx}]",
                details={"reason": str(exc)},
            ) from exc

        if len(raw) == 0:
            raise AppError(
                ErrorCode.AI_PROVIDER_ERROR,
                f"AI provider returned empty image at data[{idx}]",
            )
        if len(raw) > MAX_OUTPUT_BYTES:
            raise AppError(
                ErrorCode.AI_PROVIDER_ERROR,
                f"AI provider image exceeds {MAX_OUTPUT_BYTES // (1024*1024)} MB cap",
                details={"bytes": len(raw), "max": MAX_OUTPUT_BYTES},
            )
        out.append(raw)

    logger.info("AI gen returned %d image(s), total_bytes=%d", len(out), sum(len(b) for b in out))
    return out