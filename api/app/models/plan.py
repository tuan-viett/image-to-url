"""Plan model — pricing tiers (FREE/BASIC/PRO per PLAN §3.7)."""
from typing import List, TYPE_CHECKING

from sqlalchemy import BigInteger, Index, UniqueConstraint, Integer, String, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._base import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Plan(Base, TimestampMixin):
    """Bảng gói dịch vụ. Trường price lưu theo đơn vị xu (1 VND = 100 xu)."""

    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("name", name="uk_plans_name"),
        Index("idx_plans_sort_order", "sort_order"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "Bảng các gói dịch vụ (Free, Basic, Pro).",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False, comment="Tên gói hiển thị")
    price: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="Giá gói, lưu theo đơn vị xu (1 VND = 100 xu). Ví dụ 100000 VND = 10000000 xu.",
    )
    initial_uploads: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="Số credit upload cấp ban đầu khi user mua/nâng cấp gói này.",
    )
    retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
        comment="Số ngày ảnh được lưu trên storage trước khi tự hết hạn (cleanup cron).",
    )
    image_quality: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0",
        comment="Chế độ xử lý ảnh. 0=optimized (resize/compress), 1=original (giữ nguyên).",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="Thứ tự hiển thị (tăng dần). Dùng để sắp xếp pricing.",
    )

    users: Mapped[List["User"]] = relationship("User", back_populates="plan")