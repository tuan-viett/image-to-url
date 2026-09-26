"""Application errors and consistent error response shape (per PLAN §17)."""
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import HTTPException, status


class ErrorCode(str, Enum):
    INVALID_BASE64 = "INVALID_BASE64"
    INVALID_IMAGE = "INVALID_IMAGE"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_API_KEY = "INVALID_API_KEY"
    API_KEY_REVOKED = "API_KEY_REVOKED"
    IMAGE_NOT_FOUND = "IMAGE_NOT_FOUND"
    STORAGE_ERROR = "STORAGE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    EMAIL_TAKEN = "EMAIL_TAKEN"
    BAD_CREDENTIALS = "BAD_CREDENTIALS"
    CONFLICT = "CONFLICT"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"
    AI_CONTENT_BLOCKED = "AI_CONTENT_BLOCKED"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_DISABLED = "AI_DISABLED"


_STATUS = {
    ErrorCode.INVALID_BASE64: status.HTTP_400_BAD_REQUEST,
    ErrorCode.INVALID_IMAGE: status.HTTP_400_BAD_REQUEST,
    ErrorCode.UNSUPPORTED_FORMAT: status.HTTP_400_BAD_REQUEST,
    ErrorCode.FILE_TOO_LARGE: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.QUOTA_EXCEEDED: status.HTTP_402_PAYMENT_REQUIRED,
    ErrorCode.UNAUTHORIZED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.INVALID_API_KEY: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.API_KEY_REVOKED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.IMAGE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.STORAGE_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.EMAIL_TAKEN: status.HTTP_409_CONFLICT,
    ErrorCode.BAD_CREDENTIALS: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.CONFLICT: status.HTTP_409_CONFLICT,
    ErrorCode.AI_PROVIDER_ERROR: status.HTTP_502_BAD_GATEWAY,
    ErrorCode.AI_CONTENT_BLOCKED: status.HTTP_400_BAD_REQUEST,
    ErrorCode.AI_TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    ErrorCode.AI_DISABLED: status.HTTP_503_SERVICE_UNAVAILABLE,
}


class AppError(HTTPException):
    """Raised by services and caught by the global handler."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(
            status_code=_STATUS[code],
            detail={"code": code.value, "message": message, "details": self.details},
        )


def error_payload(code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "success": False,
        "error": {"code": code.value, "message": message, "details": details or {}},
    }