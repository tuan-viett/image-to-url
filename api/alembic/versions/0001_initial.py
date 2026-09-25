"""initial schema

Creates 7 tables per PLAN.md §7 and Baokim SQL conventions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- plans ----
    op.create_table(
        "plans",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False, comment="Tên gói hiển thị"),
        sa.Column(
            "price", sa.BigInteger(), nullable=False, server_default="0",
            comment="Giá gói, lưu theo đơn vị xu (1 VND = 100 xu). Ví dụ 100000 VND = 10000000 xu.",
        ),
        sa.Column(
            "initial_uploads", sa.Integer(), nullable=False, server_default="0",
            comment="Số credit upload cấp ban đầu khi user mua/nâng cấp gói này.",
        ),
        sa.Column(
            "retention_days", sa.Integer(), nullable=False, server_default="1",
            comment="Số ngày ảnh được lưu trên storage trước khi tự hết hạn (cleanup cron).",
        ),
        sa.Column(
            "image_quality", sa.SmallInteger(), nullable=False, server_default="0",
            comment="Chế độ xử lý ảnh. 0=optimized (resize/compress), 1=original (giữ nguyên).",
        ),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default="0",
            comment="Thứ tự hiển thị (tăng dần). Dùng để sắp xếp pricing.",
        ),
        sa.Column(
            "created", sa.DateTime(timezone=False), server_default=sa.func.current_timestamp(), nullable=False,
            comment="Thời điểm tạo bản ghi (UTC)",
        ),
        sa.Column(
            "modified", sa.DateTime(timezone=False),
            server_default=sa.func.current_timestamp(), nullable=False,
            comment="Thời điểm cập nhật bản ghi gần nhất (UTC)",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uk_plans_name"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Bảng các gói dịch vụ (Free, Basic, Pro).",
    )
    op.create_index("idx_plans_sort_order", "plans", ["sort_order"])

    # ---- users ----
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, comment="Email đăng nhập (unique)."),
        sa.Column(
            "password_hash", sa.String(length=255), nullable=False,
            comment="Hash bcrypt (cost 12) của mật khẩu.",
        ),
        sa.Column(
            "name", sa.String(length=120), nullable=False, server_default="",
            comment="Tên hiển thị.",
        ),
        sa.Column(
            "avatar_url", sa.String(length=500), nullable=True,
            comment="URL ảnh đại diện (optional).",
        ),
        sa.Column(
            "plan_id", sa.BigInteger(), nullable=False,
            comment="Gói hiện tại của user. Tham chiếu plans.id.",
        ),
        sa.Column(
            "upload_credits", sa.Integer(), nullable=False, server_default="0",
            comment="Số credit upload còn lại. Mỗi upload thành công trừ 1 credit.",
        ),
        sa.Column(
            "created", sa.DateTime(timezone=False), server_default=sa.func.current_timestamp(),
            nullable=False, comment="Thời điểm tạo bản ghi (UTC)",
        ),
        sa.Column(
            "modified", sa.DateTime(timezone=False),
            server_default=sa.func.current_timestamp(), nullable=False,
            comment="Thời điểm cập nhật bản ghi gần nhất (UTC)",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uk_users_email"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name="fk_users_plan_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Bảng người dùng. plan_id là gói hiện tại (chỉ tăng, không tự downgrade).",
    )
    op.create_index("idx_users_plan_id", "users", ["plan_id"])
    op.create_index("idx_users_created", "users", ["created"])

    # ---- api_keys ----
    op.create_table(
        "api_keys",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.BigInteger(), nullable=False,
            comment="ID user sở hữu key.",
        ),
        sa.Column(
            "name", sa.String(length=120), nullable=False, server_default="",
            comment="Tên gợi nhớ (vd: 'Production').",
        ),
        sa.Column(
            "key_prefix", sa.String(length=20), nullable=False,
            comment="Phần đầu của key (vd: 'sk_live_a1b2') hiển thị trên dashboard.",
        ),
        sa.Column(
            "key_hash", sa.String(length=255), nullable=False,
            comment="bcrypt hash của secret. KHÔNG lưu plaintext.",
        ),
        sa.Column(
            "environment", sa.SmallInteger(), nullable=False, server_default="1",
            comment="Môi trường. 1=live, 2=test.",
        ),
        sa.Column(
            "last_used_at", sa.DateTime(timezone=False), nullable=True,
            comment="Lần dùng key gần nhất (UTC). NULL = chưa dùng.",
        ),
        sa.Column(
            "created", sa.DateTime(timezone=False), server_default=sa.func.current_timestamp(),
            nullable=False, comment="Thời điểm tạo key (UTC).",
        ),
        sa.Column(
            "revoked_at", sa.DateTime(timezone=False), nullable=True,
            comment="Thời điểm revoke. NULL = còn hiệu lực.",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_prefix", name="uk_api_keys_key_prefix"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_api_keys_user_id", ondelete="CASCADE"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Bảng API key. key_hash là bcrypt(secret); plaintext chỉ trả về client 1 lần lúc tạo.",
    )
    op.create_index("idx_api_keys_user_env", "api_keys", ["user_id", "environment"])
    op.create_index("idx_api_keys_created", "api_keys", ["created"])

    # ---- images ----
    op.create_table(
        "images",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.BigInteger(), nullable=True,
            comment="ID user sở hữu ảnh. NULL = anonymous upload.",
        ),
        sa.Column(
            "storage_key", sa.String(length=64), nullable=False,
            comment="Khóa lưu trữ random (secrets.token_urlsafe(16)). KHÔNG dùng từ user input.",
        ),
        sa.Column(
            "original_filename", sa.String(length=255), nullable=False, server_default="",
            comment="Tên file gốc từ client (chỉ để hiển thị; không dùng cho URL/path).",
        ),
        sa.Column(
            "mime_type", sa.String(length=60), nullable=False,
            comment="MIME detect từ magic bytes, ví dụ: image/png, image/jpeg.",
        ),
        sa.Column(
            "size_bytes", sa.BigInteger(), nullable=False,
            comment="Kích thước file (bytes) sau khi xử lý theo image_quality.",
        ),
        sa.Column(
            "width", sa.Integer(), nullable=False, server_default="0",
            comment="Chiều rộng (pixel).",
        ),
        sa.Column(
            "height", sa.Integer(), nullable=False, server_default="0",
            comment="Chiều cao (pixel).",
        ),
        sa.Column(
            "hash", sa.CHAR(length=64), nullable=False,
            comment="SHA-256 hex của nội dung file (để dedupe, integrity).",
        ),
        sa.Column(
            "public_url", sa.String(length=500), nullable=False,
            comment="URL public trả về cho client. Format: {PUBLIC_IMAGE_BASE_URL}/{key}.{ext}",
        ),
        sa.Column(
            "source", sa.SmallInteger(), nullable=False,
            comment="Nguồn upload. 1=anonymous_upload, 2=web_upload, 3=base64, 4=api.",
        ),
        sa.Column(
            "image_quality", sa.SmallInteger(), nullable=False,
            comment="Chế độ xử lý ảnh tại thời điểm upload. 0=optimized, 1=original.",
        ),
        sa.Column(
            "created", sa.DateTime(timezone=False), server_default=sa.func.current_timestamp(),
            nullable=False, comment="Thời điểm upload (UTC).",
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=False), nullable=False,
            comment="Thời điểm hết hạn bắt buộc = created + plan.retention_days (UTC).",
        ),
        sa.Column(
            "deleted_at", sa.DateTime(timezone=False), nullable=True,
            comment="Soft delete timestamp. NULL = chưa xóa.",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uk_images_storage_key"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_images_user_id", ondelete="SET NULL"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Bảng ảnh đã upload. expires_at bắt buộc, = created + plan.retention_days.",
    )
    op.create_index("idx_images_user_created", "images", ["user_id", "created"])
    op.create_index("idx_images_expires_active", "images", ["expires_at", "deleted_at"])
    op.create_index("idx_images_created", "images", ["created"])

    # ---- upload_credit_transactions ----
    op.create_table(
        "upload_credit_transactions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="ID user bị ảnh hưởng."),
        sa.Column(
            "type", sa.SmallInteger(), nullable=False,
            comment="Loại giao dịch. 1=PLAN_GRANT, 2=TOPUP, 3=UPLOAD, 4=ADMIN_ADJUSTMENT, 5=REFUND.",
        ),
        sa.Column(
            "amount", sa.Integer(), nullable=False,
            comment="Số credit thay đổi. Có thể âm (vd: UPLOAD = -1, REFUND có thể +).",
        ),
        sa.Column(
            "balance_after", sa.Integer(), nullable=False,
            comment="Số dư credit của user ngay sau giao dịch này.",
        ),
        sa.Column(
            "reference_type", sa.String(length=60), nullable=True,
            comment="Loại tham chiếu (vd: 'plan', 'payment', 'image'). NULL nếu không có.",
        ),
        sa.Column(
            "reference_id", sa.BigInteger(), nullable=True,
            comment="ID tham chiếu tới bản ghi liên quan (vd: image.id). NULL nếu không có.",
        ),
        sa.Column(
            "created", sa.DateTime(timezone=False), server_default=sa.func.current_timestamp(),
            nullable=False, comment="Thời điểm ghi nhận giao dịch (UTC).",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_upload_credit_user_id", ondelete="CASCADE"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Bảng lịch sử biến động upload credits. amount có thể âm (vd: UPLOAD).",
    )
    op.create_index("idx_upload_credit_user_created", "upload_credit_transactions", ["user_id", "created"])

    # ---- payments ----
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="ID user thực hiện thanh toán."),
        sa.Column(
            "type", sa.SmallInteger(), nullable=False,
            comment="Loại thanh toán. 1=PLAN_UPGRADE (nâng cấp gói), 2=CREDIT_TOPUP (mua thêm credit).",
        ),
        sa.Column(
            "amount", sa.BigInteger(), nullable=False,
            comment="Số tiền, lưu theo đơn vị xu (1 VND = 100 xu).",
        ),
        sa.Column(
            "currency", sa.CHAR(length=3), nullable=False, server_default="VND",
            comment="Mã tiền tệ ISO 4217 (3 ký tự). Mặc định VND.",
        ),
        sa.Column(
            "status", sa.SmallInteger(), nullable=False, server_default="1",
            comment="Trạng thái. 1=pending, 2=completed, 3=refunded, 4=failed.",
        ),
        sa.Column(
            "provider", sa.String(length=60), nullable=False, server_default="mock",
            comment="Tên payment provider (vd: 'stripe', 'mock').",
        ),
        sa.Column(
            "provider_transaction_id", sa.String(length=120), nullable=True,
            comment="ID giao dịch phía payment provider (vd: Stripe charge id).",
        ),
        sa.Column(
            "reference_type", sa.String(length=60), nullable=True,
            comment="Loại tham chiếu (vd: 'plan', 'credit_topup'). NULL nếu không có.",
        ),
        sa.Column(
            "reference_id", sa.BigInteger(), nullable=True,
            comment="ID tham chiếu (vd: plans.id khi upgrade).",
        ),
        sa.Column(
            "created", sa.DateTime(timezone=False), server_default=sa.func.current_timestamp(),
            nullable=False, comment="Thời điểm tạo thanh toán (UTC).",
        ),
        sa.Column(
            "modified", sa.DateTime(timezone=False),
            server_default=sa.func.current_timestamp(), nullable=False,
            comment="Thời điểm cập nhật trạng thái thanh toán (UTC).",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_payments_user_id", ondelete="CASCADE"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Bảng thanh toán. MVP chỉ hỗ trợ mua một lần, không subscription.",
    )
    op.create_index("idx_payments_user_created", "payments", ["user_id", "created"])
    op.create_index("idx_payments_status", "payments", ["status"])

    # ---- usage_events ----
    op.create_table(
        "usage_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id", sa.BigInteger(), nullable=True,
            comment="ID user liên quan. NULL = anonymous.",
        ),
        sa.Column(
            "api_key_id", sa.BigInteger(), nullable=True,
            comment="ID API key (nếu request qua API). NULL nếu dùng JWT hoặc anonymous.",
        ),
        sa.Column(
            "event_type", sa.SmallInteger(), nullable=False,
            comment="Loại sự kiện. 1=upload, 2=api_request, 3=delete, 4=failed_upload, 5=image_expired.",
        ),
        sa.Column(
            "bytes", sa.BigInteger(), nullable=False, server_default="0",
            comment="Số bytes liên quan (vd: size của file upload).",
        ),
        sa.Column(
            "metadata_json", sa.JSON(), nullable=True,
            comment="Metadata bổ sung dạng JSON (vd: error code, image_id).",
        ),
        sa.Column(
            "created", sa.DateTime(timezone=False), server_default=sa.func.current_timestamp(),
            nullable=False, comment="Thời điểm xảy ra sự kiện (UTC).",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_usage_events_user_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"], ["api_keys.id"], name="fk_usage_events_api_key_id", ondelete="SET NULL"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="Bảng audit log cho usage events (upload, delete, v.v.).",
    )
    op.create_index("idx_usage_events_user_created", "usage_events", ["user_id", "created"])
    op.create_index("idx_usage_events_api_key", "usage_events", ["api_key_id"])
    op.create_index("idx_usage_events_type_created", "usage_events", ["event_type", "created"])


def downgrade() -> None:
    op.drop_index("idx_usage_events_type_created", table_name="usage_events")
    op.drop_index("idx_usage_events_api_key", table_name="usage_events")
    op.drop_index("idx_usage_events_user_created", table_name="usage_events")
    op.drop_table("usage_events")

    op.drop_index("idx_payments_status", table_name="payments")
    op.drop_index("idx_payments_user_created", table_name="payments")
    op.drop_table("payments")

    op.drop_index("idx_upload_credit_user_created", table_name="upload_credit_transactions")
    op.drop_table("upload_credit_transactions")

    op.drop_index("idx_images_created", table_name="images")
    op.drop_index("idx_images_expires_active", table_name="images")
    op.drop_index("idx_images_user_created", table_name="images")
    op.drop_table("images")

    op.drop_index("idx_api_keys_created", table_name="api_keys")
    op.drop_index("idx_api_keys_user_env", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index("idx_users_created", table_name="users")
    op.drop_index("idx_users_plan_id", table_name="users")
    op.drop_table("users")

    op.drop_index("idx_plans_sort_order", table_name="plans")
    op.drop_table("plans")