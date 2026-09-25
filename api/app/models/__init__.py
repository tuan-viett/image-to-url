"""SQLAlchemy ORM models.

Schema follows PLAN.md §7 with Baokim SQL conventions:
  - snake_case, plural table names (≤24 chars)
  - BIGINT UNSIGNED for money with comment "đơn vị xu"
  - DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP for created/modified
  - utf8mb4_unicode_ci on string columns
  - Indexes: idx_<cols>, uk_<cols>, fk_<tbl>_<cols>
"""
from app.models.plan import Plan
from app.models.user import User
from app.models.image import Image
from app.models.api_key import ApiKey
from app.models.upload_credit import UploadCreditTransaction
from app.models.config import Config
from app.models.payment import Payment
from app.models.usage_event import UsageEvent

__all__ = [
    "Config",
    "Plan",
    "User",
    "Image",
    "ApiKey",
    "UploadCreditTransaction",
    "Payment",
    "UsageEvent",
]