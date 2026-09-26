"""AI Image Generation — cập nhật comment cho 3 cột enum để document giá trị mới.

Không đổi schema (vẫn là TINYINT/SmallInteger không có CHECK constraint), chỉ
sửa COMMENT để người đọc biết có thêm giá trị ``5=ai_generated`` / ``6=ai_generation``.

Cột update:
  - ``images.source``             + ``5=ai_generated``
  - ``usage_events.event_type``   + ``6=ai_generation``
  - ``upload_credit_transactions.type``  + ``6=AI_GENERATION``

Seed các config key mới (ai_image.*) đã có trong ``app/seed.py`` — chạy
``python -m app.seed`` sau khi upgrade để chèn 5 row placeholder.
"""
from typing import Sequence, Union as _Union

from alembic import op


revision: str = "0003_ai_image_generation"
down_revision: _Union[str, None] = "0002_payment_sepay"
branch_labels: _Union[str, Sequence[str], None] = None
depends_on: _Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # images.source — thêm 5=ai_generated. Cột là SMALLINT (model maps SmallInteger).
    op.execute(
        "ALTER TABLE images "
        "MODIFY COLUMN source SMALLINT NOT NULL DEFAULT 1 "
        "COMMENT 'Nguồn upload: 1=anonymous_upload, 2=web_upload, 3=base64, 4=api, 5=ai_generated.'"
    )
    # usage_events.event_type — thêm 6=ai_generation
    op.execute(
        "ALTER TABLE usage_events "
        "MODIFY COLUMN event_type SMALLINT NOT NULL "
        "COMMENT 'Loại sự kiện. 1=upload, 2=api_request, 3=delete, 4=failed_upload, 5=image_expired, 6=ai_generation.'"
    )
    # upload_credit_transactions.type — thêm 6=AI_GENERATION
    op.execute(
        "ALTER TABLE upload_credit_transactions "
        "MODIFY COLUMN type SMALLINT NOT NULL "
        "COMMENT 'Loại giao dịch credit. 1=PLAN_GRANT, 2=TOPUP, 3=UPLOAD, 4=ADMIN_ADJUSTMENT, 5=REFUND, 6=AI_GENERATION.'"
    )


def downgrade() -> None:
    # Rollback về comment cũ — không xóa data, không khóa history table
    op.execute(
        "ALTER TABLE images "
        "MODIFY COLUMN source SMALLINT NOT NULL DEFAULT 1 "
        "COMMENT 'Nguồn upload. 1=anonymous_upload, 2=web_upload, 3=base64, 4=api.'"
    )
    op.execute(
        "ALTER TABLE usage_events "
        "MODIFY COLUMN event_type SMALLINT NOT NULL "
        "COMMENT 'Loại sự kiện. 1=upload, 2=api_request, 3=delete, 4=failed_upload, 5=image_expired.'"
    )
    op.execute(
        "ALTER TABLE upload_credit_transactions "
        "MODIFY COLUMN type SMALLINT NOT NULL "
        "COMMENT 'Loại giao dịch. 1=PLAN_GRANT, 2=TOPUP, 3=UPLOAD, 4=ADMIN_ADJUSTMENT, 5=REFUND.'"
    )