"""Application configuration loaded from environment variables.

All secrets come from .env (provided via env_file in docker-compose).
"""
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="mysql+pymysql://imageurl:imageurl_pwd@mysql:3306/imageurl?charset=utf8mb4",
        alias="DATABASE_URL",
    )

    # JWT
    jwt_secret: str = Field(default="change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_ttl_minutes: int = Field(default=60, alias="JWT_ACCESS_TTL_MINUTES")

    # Storage
    storage_root: str = Field(default="/data/uploads", alias="STORAGE_ROOT")
    public_image_base_url: str = Field(
        default="http://localhost/i", alias="PUBLIC_IMAGE_BASE_URL"
    )

    # Limits
    anon_max_file_bytes: int = Field(default=5_242_880, alias="ANON_MAX_FILE_BYTES")
    anon_daily_limit: int = Field(default=10, alias="ANON_DAILY_LIMIT")
    anon_retention_days: int = Field(default=1, alias="ANON_RETENTION_DAYS")
    auth_max_file_bytes: int = Field(default=10_485_760, alias="AUTH_MAX_FILE_BYTES")
    max_pixels: int = Field(default=50_000_000, alias="MAX_PIXELS")

    # CORS
    allowed_origins: str = Field(default="http://localhost", alias="ALLOWED_ORIGINS")

    # Worker
    worker_batch_size: int = Field(default=100, alias="WORKER_BATCH_SIZE")
    worker_interval_minutes: int = Field(default=60, alias="WORKER_INTERVAL_MINUTES")

    # Demo seed
    demo_user_email: str = Field(default="demo@example.com", alias="DEMO_USER_EMAIL")
    demo_user_password: str = Field(default="Demo123!", alias="DEMO_USER_PASSWORD")
    demo_user_name: str = Field(default="Demo Account", alias="DEMO_USER_NAME")

    # NOTE: SePay config (bank, account, webhook secret, api_key, ...) lấy từ
    # bảng ``configs`` — KHÔNG đọc env. Xem ``app.services.sepay.load_sepay_account``
    # và ``resolve_webhook_*``. Đổi giá trị runtime: UPDATE configs SET
    # config_value='...' WHERE config_key='sepay.*'.

    @field_validator("allowed_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()