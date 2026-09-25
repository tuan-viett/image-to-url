"""Base mixins shared by all models."""
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds `created` and `modified` DATETIME columns with CURRENT_TIMESTAMP defaults."""

    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        comment="Thời điểm tạo bản ghi (UTC)",
    )
    modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        comment="Thời điểm cập nhật bản ghi gần nhất (UTC)",
    )