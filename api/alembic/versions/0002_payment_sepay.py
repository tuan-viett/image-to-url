"""Payment SePay integration

Adds:
  1. `configs` table — generic key/value store (used for bank account info,
     webhook secret overrides, etc.).
  2. Extra columns on `payments`:
     - `code` (UNIQUE)              — nội dung CK user phải ghi khi chuyển
     - `plan_id` (FK)               — gói cần nâng cấp (khi type=PLAN_UPGRADE)
     - `credits`                    — số credit cần cộng (khi type=CREDIT_TOPUP)
     - `qr_payload`                 — URL QR SePay (trả cho frontend)
     - `sepay_id`                   — id giao dịch từ webhook
     - `sepay_account_number`       — TK nhận (snapshot tại thời điểm tạo đơn)
     - `sepay_content_received`     — content giao dịch SePay trả về
     - `paid_at`                    — thời điểm webhook xác nhận
     - `expires_at`                 — timeout QR (mặc định 15 phút)

Reference: https://docs.sepay.vn/tich-hop-webhook
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_payment_sepay"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- configs ----
    op.create_table(
        "configs",
        sa.Column(
            "config_key", sa.String(length=64), nullable=False,
            comment="Khóa cấu hình (vd: sepay.bank_account, sepay.webhook_secret).",
        ),
        sa.Column(
            "config_value", sa.Text(), nullable=False,
            comment="Giá trị cấu hình (text). Secret nên lưu env, bảng này là fallback cho dev.",
        ),
        sa.Column(
            "description", sa.String(length=255), nullable=True,
            comment="Mô tả tiếng Việt cho người vận hành.",
        ),
        sa.Column(
            "created", sa.DateTime(timezone=False),
            server_default=sa.func.current_timestamp(), nullable=False,
            comment="Thời điểm tạo bản ghi (UTC).",
        ),
        sa.Column(
            "modified", sa.DateTime(timezone=False),
            server_default=sa.func.current_timestamp(), nullable=False,
            comment="Thời điểm cập nhật bản ghi gần nhất (UTC).",
        ),
        sa.PrimaryKeyConstraint("config_key"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Bảng key/value lưu cấu hình runtime (bank account, webhook secret, ...).",
    )

    # ---- payments extra columns ----
    op.add_column(
        "payments",
        sa.Column(
            "code", sa.String(length=64), nullable=True,
            comment="Mã nội dung CK mà user cần ghi khi chuyển khoản (UNIQUE).",
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "plan_id", sa.BigInteger(), nullable=True,
            comment="ID gói cần nâng cấp (khi type=PLAN_UPGRADE). NULL với CREDIT_TOPUP.",
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "credits", sa.Integer(), nullable=True,
            comment="Số credit cần cộng khi thanh toán thành công (khi type=CREDIT_TOPUP).",
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "qr_payload", sa.Text(), nullable=True,
            comment="URL ảnh QR SePay trả cho frontend khi tạo đơn.",
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "sepay_id", sa.BigInteger(), nullable=True,
            comment="ID giao dịch từ SePay (set khi webhook xác nhận thanh toán).",
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "sepay_account_number", sa.String(length=60), nullable=True,
            comment="Số TK nhận snapshot tại thời điểm tạo đơn (đối soát).",
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "sepay_content_received", sa.String(length=255), nullable=True,
            comment="Nội dung CK thực tế SePay trả về từ webhook.",
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "paid_at", sa.DateTime(timezone=False), nullable=True,
            comment="Thời điểm webhook xác nhận đã nhận tiền (UTC).",
        ),
    )
    op.add_column(
        "payments",
        sa.Column(
            "expires_at", sa.DateTime(timezone=False), nullable=True,
            comment="Thời điểm QR hết hạn (UTC). Mặc định 15 phút sau khi tạo đơn.",
        ),
    )

    # UNIQUE index on payments.code (only non-null values, MySQL handles NULLs fine)
    op.create_index("uk_payments_code", "payments", ["code"], unique=True)

    # FK payments.plan_id -> plans.id
    op.create_foreign_key(
        "fk_payments_plan_id",
        "payments", "plans",
        ["plan_id"], ["id"],
        ondelete="SET NULL",
    )

    # Index on status + expires_at for cleanup cron
    op.create_index(
        "idx_payments_status_expires",
        "payments",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_payments_status_expires", table_name="payments")
    op.drop_constraint("fk_payments_plan_id", "payments", type_="foreignkey")
    op.drop_index("uk_payments_code", table_name="payments")
    op.drop_column("payments", "expires_at")
    op.drop_column("payments", "paid_at")
    op.drop_column("payments", "sepay_content_received")
    op.drop_column("payments", "sepay_account_number")
    op.drop_column("payments", "sepay_id")
    op.drop_column("payments", "qr_payload")
    op.drop_column("payments", "credits")
    op.drop_column("payments", "plan_id")
    op.drop_column("payments", "code")
    op.drop_table("configs")