"""Auth + user schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    avatar_url: Optional[str]
    plan_id: int
    upload_credits: int
    # Quota tổng mà plan hiện tại cấp. Tính remaining bằng upload_credits,
    # used = plan_initial_uploads - upload_credits (cho user chưa từng nâng cấp).
    # User đã renewal nhiều lần → quota tích luỹ lớn hơn initial_uploads → có thể âm.
    plan_initial_uploads: int
    plan_name: str
    plan_sort_order: int
    plan_retention_days: int
    plan_image_quality: int
    created: datetime
    modified: datetime

    class Config:
        from_attributes = True


class AuthOut(BaseModel):
    user: UserOut
    access_token: str
    token_type: str = "Bearer"
    expires_in: int