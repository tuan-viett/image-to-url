"""Upload-credit transaction log (audit trail for every credit change)."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class UploadCreditTransaction(Base):
    """Bảng lịch sử biến động credit của user. Mọi thay đổi credit đều phải ghi vào đây."""

    __tablename__ = "upload_credit_transactions"
    __table_args__ = (
        Index("idx_upload_credit_user_created", "user_id", "created"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "Bảng lịch sử biến động upload credits. amount có thể âm (vd: UPLOAD).",
        },
    )

    # Type constants
    TYPE_PLAN_GRANT = 1
    TYPE_TOPUP = 2
    TYPE_UPLOAD = 3
    TYPE_ADMIN_ADJUSTMENT = 4
    TYPE_REFUND = 5
    TYPE_AI_GENERATION = 6

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", name="fk_upload_credit_user_id", ondelete="CASCADE"),
        nullable=False, comment="ID user bị ảnh hưởng.",
    )
    type: Mapped[int] = mapped_column(
        SmallInteger, nullable=False,
        comment="Loại giao dịch. 1=PLAN_GRANT, 2=TOPUP, 3=UPLOAD, 4=ADMIN_ADJUSTMENT, 5=REFUND, 6=AI_GENERATION.",
    )
    amount: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="Số credit thay đổi. Có thể âm (vd: UPLOAD = -1, REFUND có thể +).",
    )
    balance_after: Mapped[int] = mapped_column(
        Integer, nullable=False,
        comment="Số dư credit của user ngay sau giao dịch này.",
    )
    reference_type: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True,
        comment="Loại tham chiếu (vd: 'plan', 'payment', 'image'). NULL nếu không có.",
    )
    reference_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
        comment="ID tham chiếu tới bản ghi liên quan (vd: image.id). NULL nếu không có.",
    )
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.current_timestamp(),
        comment="Thời điểm ghi nhận giao dịch (UTC).",
    )

    user: Mapped["User"] = relationship("User", back_populates="credit_transactions")