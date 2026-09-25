"""Image model — every uploaded image (anonymous or authenticated)."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CHAR,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Image(Base):
    """Bảng ảnh đã upload. user_id NULL = anonymous upload."""

    __tablename__ = "images"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uk_images_storage_key"),
        Index("idx_images_user_created", "user_id", "created"),
        Index("idx_images_expires_active", "expires_at", "deleted_at"),
        Index("idx_images_created", "created"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "Bảng ảnh đã upload. expires_at bắt buộc, = created + plan.retention_days.",
        },
    )

    # Source constants (stored in `source` column)
    SOURCE_ANONYMOUS_UPLOAD = 1
    SOURCE_WEB_UPLOAD = 2
    SOURCE_BASE64 = 3
    SOURCE_API = 4

    # Image quality constants (stored in `image_quality` column)
    QUALITY_OPTIMIZED = 0
    QUALITY_ORIGINAL = 1

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", name="fk_images_user_id", ondelete="SET NULL"),
        nullable=True, comment="ID user sở hữu ảnh. NULL = anonymous upload.",
    )
    storage_key: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="Khóa lưu trữ random (secrets.token_urlsafe(16)). KHÔNG dùng từ user input.",
    )
    original_filename: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="",
        comment="Tên file gốc từ client (chỉ để hiển thị; không dùng cho URL/path).",
    )
    mime_type: Mapped[str] = mapped_column(
        String(60), nullable=False,
        comment="MIME detect từ magic bytes, ví dụ: image/png, image/jpeg.",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Kích thước file (bytes) sau khi xử lý theo image_quality.",
    )
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="Chiều rộng (pixel).")
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="Chiều cao (pixel).")
    hash: Mapped[str] = mapped_column(
        CHAR(64), nullable=False,
        comment="SHA-256 hex của nội dung file (để dedupe, integrity).",
    )
    public_url: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="URL public trả về cho client. Format: {PUBLIC_IMAGE_BASE_URL}/{key}.{ext}",
    )
    source: Mapped[int] = mapped_column(
        SmallInteger, nullable=False,
        comment="Nguồn upload. 1=anonymous_upload, 2=web_upload, 3=base64, 4=api.",
    )
    image_quality: Mapped[int] = mapped_column(
        SmallInteger, nullable=False,
        comment="Chế độ xử lý ảnh tại thời điểm upload. 0=optimized, 1=original.",
    )
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.current_timestamp(),
        comment="Thời điểm upload (UTC).",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False,
        comment="Thời điểm hết hạn bắt buộc = created + plan.retention_days (UTC).",
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True,
        comment="Soft delete timestamp. NULL = chưa xóa.",
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="images")