"""Usage event — optional audit/observability log. Not source of truth for credits."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    SmallInteger,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.api_key import ApiKey


class UsageEvent(Base):
    """Bảng sự kiện sử dụng (observability). Không phải source of truth cho credit/usage quota."""

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("idx_usage_events_user_created", "user_id", "created"),
        Index("idx_usage_events_api_key", "api_key_id"),
        Index("idx_usage_events_type_created", "event_type", "created"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "Bảng audit log cho usage events (upload, delete, v.v.).",
        },
    )

    # Event types
    TYPE_UPLOAD = 1
    TYPE_API_REQUEST = 2
    TYPE_DELETE = 3
    TYPE_FAILED_UPLOAD = 4
    TYPE_IMAGE_EXPIRED = 5
    TYPE_AI_GENERATION = 6

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", name="fk_usage_events_user_id", ondelete="SET NULL"),
        nullable=True, comment="ID user liên quan. NULL = anonymous.",
    )
    api_key_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("api_keys.id", name="fk_usage_events_api_key_id", ondelete="SET NULL"),
        nullable=True, comment="ID API key (nếu request qua API). NULL nếu dùng JWT hoặc anonymous.",
    )
    event_type: Mapped[int] = mapped_column(
        SmallInteger, nullable=False,
        comment="Loại sự kiện. 1=upload, 2=api_request, 3=delete, 4=failed_upload, 5=image_expired, 6=ai_generation.",
    )
    bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0",
        comment="Số bytes liên quan (vd: size của file upload).",
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True,
        comment="Metadata bổ sung dạng JSON (vd: error code, image_id).",
    )
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.current_timestamp(),
        comment="Thời điểm xảy ra sự kiện (UTC).",
    )

    user: Mapped[Optional["User"]] = relationship("User")
    api_key: Mapped[Optional["ApiKey"]] = relationship("ApiKey")