"""Usage + plan + payment schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UsageCounter(BaseModel):
    event_type: int
    event_type_label: str
    count: int
    bytes_total: int


class UsageOut(BaseModel):
    counters: list[UsageCounter]
    upload_credits_remaining: int
    plan_name: str


class PlanOut(BaseModel):
    id: int
    name: str
    price: int  # xu (1 VND = 100 xu)
    initial_uploads: int
    retention_days: int
    image_quality: int
    sort_order: int

    class Config:
        from_attributes = True


class PaymentUpgradeIn(BaseModel):
    plan_id: int = Field(ge=1)
    environment: int = Field(default=1, description="Reserved for future use")


class PaymentOut(BaseModel):
    id: int
    type: int
    amount: int
    currency: str
    status: int
    provider: str
    reference_type: Optional[str]
    reference_id: Optional[int]
    created: datetime

    # SePay fields (migration 0002)
    code: Optional[str] = None
    plan_id: Optional[int] = None
    credits: Optional[int] = None
    qr_payload: Optional[str] = None
    sepay_id: Optional[int] = None
    sepay_account_number: Optional[str] = None
    sepay_content_received: Optional[str] = None
    paid_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SepayOrderOut(BaseModel):
    """Response khi tạo đơn thanh toán SePay QR (POST /payments/upgrade)."""
    payment: PaymentOut
    qr_image_url: str
    bank_code: str
    account_number: str
    account_name: str
    amount_vnd: int
    description: str
    expires_at: datetime
    seconds_remaining: int


class SepayStatusOut(BaseModel):
    """Response khi frontend polling trạng thái (GET /payments/{id}/status)."""
    payment_id: int
    status: int
    is_paid: bool
    is_expired: bool
    paid_at: Optional[datetime] = None
    plan_id: Optional[int] = None
    credits: Optional[int] = None


class SepayConfigOut(BaseModel):
    """Config SePay public (ẩn secret). Dùng để debug trên frontend."""
    bank_code: str
    account_number: str
    account_name: str
    template: str
    qr_ttl_minutes: int


class PublicLimitsOut(BaseModel):
    """Giới hạn hệ thống — lấy từ Settings (env). Public để landing page render
    placeholder không phải hardcode số MB / retention hours."""
    anon_max_file_mb: int
    auth_max_file_mb: int
    anon_retention_hours: int


class PublicConfigOut(BaseModel):
    """Single source of truth cho landing page: giới hạn hệ thống + danh sách
    plan active. Public, không cần auth. Đổi Settings (env) hoặc plans (DB) là
    tất cả client tự pick up — không sửa HTML."""
    limits: PublicLimitsOut
    plans: list[PlanOut]