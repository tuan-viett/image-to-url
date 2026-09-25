"""User model."""
from typing import List, TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._base import TimestampMixin

if TYPE_CHECKING:
    from app.models.plan import Plan
    from app.models.image import Image
    from app.models.api_key import ApiKey
    from app.models.upload_credit import UploadCreditTransaction
    from app.models.payment import Payment


class User(Base, TimestampMixin):
    """Bảng người dùng đã đăng ký."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uk_users_email"),
        Index("idx_users_plan_id", "plan_id"),
        Index("idx_users_created", "created"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "Bảng người dùng. plan_id là gói hiện tại (chỉ tăng, không tự downgrade).",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, comment="Email đăng nhập (unique).")
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Hash bcrypt (cost 12) của mật khẩu."
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="", comment="Tên hiển thị.")
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="URL ảnh đại diện (optional).")
    plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("plans.id", name="fk_users_plan_id"), nullable=False,
        comment="Gói hiện tại của user. Tham chiếu plans.id.",
    )
    upload_credits: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="Số credit upload còn lại. Mỗi upload thành công trừ 1 credit.",
    )

    plan: Mapped["Plan"] = relationship("Plan", back_populates="users", lazy="joined")
    images: Mapped[List["Image"]] = relationship("Image", back_populates="user")
    api_keys: Mapped[List["ApiKey"]] = relationship("ApiKey", back_populates="user")
    credit_transactions: Mapped[List["UploadCreditTransaction"]] = relationship(
        "UploadCreditTransaction", back_populates="user"
    )
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="user")