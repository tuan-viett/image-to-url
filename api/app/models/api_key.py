"""API key model."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ApiKey(Base):
    """Bảng API key của user. Chỉ lưu bcrypt hash của secret, không bao giờ lưu plaintext."""

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_prefix", name="uk_api_keys_key_prefix"),
        Index("idx_api_keys_user_env", "user_id", "environment"),
        Index("idx_api_keys_created", "created"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "Bảng API key. key_hash là bcrypt(secret); plaintext chỉ trả về client 1 lần lúc tạo.",
        },
    )

    # Environment constants
    ENV_LIVE = 1
    ENV_TEST = 2

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", name="fk_api_keys_user_id", ondelete="CASCADE"),
        nullable=False, comment="ID user sở hữu key.",
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="", comment="Tên gợi nhớ (vd: 'Production').")
    key_prefix: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="Phần đầu của key (vd: 'sk_live_a1b2') hiển thị trên dashboard để phân biệt các key.",
    )
    key_hash: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="bcrypt hash của secret. KHÔNG lưu plaintext.",
    )
    environment: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1",
        comment="Môi trường. 1=live, 2=test.",
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True,
        comment="Lần dùng key gần nhất (UTC). NULL = chưa dùng.",
    )
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.current_timestamp(),
        comment="Thời điểm tạo key (UTC).",
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True,
        comment="Thời điểm revoke. NULL = còn hiệu lực.",
    )

    user: Mapped["User"] = relationship("User", back_populates="api_keys")