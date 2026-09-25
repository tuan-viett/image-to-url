"""Runtime config (key/value) — bank account, webhook secret override, etc.

Generic store so we don't need a migration for every new setting. Hot values
come from environment; this table is the dev fallback documented in seed.py.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Config(Base):
    """Bảng key/value lưu cấu hình runtime.

    Mỗi bản ghi là một cặp ``config_key`` (PK) / ``config_value`` (TEXT).
    Secret (vd: webhook secret) mặc định lấy từ env; bảng này là fallback cho dev.
    """

    __tablename__ = "configs"
    __table_args__ = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
        "comment": "Bảng key/value lưu cấu hình runtime (bank account, webhook secret, ...).",
    }

    config_key: Mapped[str] = mapped_column(
        String(64), primary_key=True,
        comment="Khóa cấu hình (vd: sepay.bank_account, sepay.webhook_secret).",
    )
    config_value: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Giá trị cấu hình (text). Secret nên lưu env, bảng này là fallback cho dev.",
    )
    description: Mapped[str] = mapped_column(
        String(255), nullable=True, default="",
        comment="Mô tả tiếng Việt cho người vận hành.",
    )
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.current_timestamp(),
        comment="Thời điểm tạo bản ghi (UTC).",
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        comment="Thời điểm cập nhật bản ghi gần nhất (UTC).",
    )

    # Known keys (constants for typo-safety)
    KEY_SEPAY_BANK = "sepay.bank"
    KEY_SEPAY_ACCOUNT = "sepay.account_number"
    KEY_SEPAY_ACCOUNT_NAME = "sepay.account_name"
    KEY_SEPAY_TEMPLATE = "sepay.template"   # compact | print | qr_only
    KEY_SEPAY_WEBHOOK_SECRET = "sepay.webhook_secret"
    KEY_SEPAY_WEBHOOK_API_KEY = "sepay.api_key"
    KEY_SEPAY_QR_TTL_MINUTES = "sepay.qr_ttl_minutes"
    KEY_SEPAY_STORE = "sepay.store_name"     # tên cửa hàng hiển thị trên VietQR (optional)