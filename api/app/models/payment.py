"""Payment model — one-time purchases (no subscription in MVP per PLAN §3.7).

Schema augmented for SePay QR payment integration (migration 0002):
- ``code``                    — nội dung CK user phải ghi khi chuyển khoản (UNIQUE).
- ``plan_id`` / ``credits``   — snapshot sản phẩm cần deliver khi webhook xác nhận.
- ``qr_payload``              — URL QR SePay trả cho frontend.
- ``sepay_*``                 — metadata giao dịch nhận từ webhook.
- ``paid_at`` / ``expires_at``— timestamp webhook xác nhận / timeout QR.
"""
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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models._base import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.plan import Plan


class Payment(Base, TimestampMixin):
    """Bảng thanh toán. MVP chỉ hỗ trợ one-time purchase (PLAN_UPGRADE / CREDIT_TOPUP)."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("code", name="uk_payments_code"),
        Index("idx_payments_user_created", "user_id", "created"),
        Index("idx_payments_status", "status"),
        Index("idx_payments_status_expires", "status", "expires_at"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
            "comment": "Bảng thanh toán. MVP chỉ hỗ trợ mua một lần, không subscription.",
        },
    )

    # Type constants
    TYPE_PLAN_UPGRADE = 1
    TYPE_CREDIT_TOPUP = 2

    # Status constants
    STATUS_PENDING = 1
    STATUS_COMPLETED = 2
    STATUS_REFUNDED = 3
    STATUS_FAILED = 4
    STATUS_EXPIRED = 5

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", name="fk_payments_user_id", ondelete="CASCADE"),
        nullable=False, comment="ID user thực hiện thanh toán.",
    )
    type: Mapped[int] = mapped_column(
        SmallInteger, nullable=False,
        comment="Loại thanh toán. 1=PLAN_UPGRADE (nâng cấp gói), 2=CREDIT_TOPUP (mua thêm credit).",
    )
    amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False,
        comment="Số tiền, lưu theo đơn vị xu (1 VND = 100 xu).",
    )
    currency: Mapped[str] = mapped_column(
        CHAR(3), nullable=False, default="VND", server_default="VND",
        comment="Mã tiền tệ ISO 4217 (3 ký tự). Mặc định VND.",
    )
    status: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1",
        comment=(
            "Trạng thái. 1=pending, 2=completed, 3=refunded, 4=failed, "
            "5=expired (QR hết hạn)."
        ),
    )
    provider: Mapped[str] = mapped_column(
        String(60), nullable=False, default="sepay", server_default="sepay",
        comment="Tên payment provider (vd: 'sepay', 'mock').",
    )
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True,
        comment="ID giao dịch phía payment provider (vd: SePay id từ webhook).",
    )
    reference_type: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True,
        comment="Loại tham chiếu (vd: 'plan', 'credit_topup'). NULL nếu không có.",
    )
    reference_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
        comment="ID tham chiếu (vd: plans.id khi upgrade).",
    )

    # ---- SePay-specific columns (migration 0002) ----
    code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment="Mã nội dung CK mà user cần ghi khi chuyển khoản (UNIQUE).",
    )
    plan_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("plans.id", name="fk_payments_plan_id", ondelete="SET NULL"),
        nullable=True,
        comment="ID gói cần nâng cấp (khi type=PLAN_UPGRADE). NULL với CREDIT_TOPUP.",
    )
    credits: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Số credit cần cộng khi thanh toán thành công (khi type=CREDIT_TOPUP).",
    )
    qr_payload: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="URL ảnh QR SePay trả cho frontend khi tạo đơn.",
    )
    sepay_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True,
        comment="ID giao dịch từ SePay (set khi webhook xác nhận thanh toán).",
    )
    sepay_account_number: Mapped[Optional[str]] = mapped_column(
        String(60), nullable=True,
        comment="Số TK nhận snapshot tại thời điểm tạo đơn (đối soát).",
    )
    sepay_content_received: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Nội dung CK thực tế SePay trả về từ webhook.",
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True,
        comment="Thời điểm webhook xác nhận đã nhận tiền (UTC).",
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False), nullable=True,
        comment="Thời điểm QR hết hạn (UTC). Mặc định 15 phút sau khi tạo đơn.",
    )

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.current_timestamp(),
        comment="Thời điểm tạo thanh toán (UTC).",
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        comment="Thời điểm cập nhật trạng thái thanh toán (UTC).",
    )

    user: Mapped["User"] = relationship("User", back_populates="payments")
    plan: Mapped[Optional["Plan"]] = relationship("Plan")