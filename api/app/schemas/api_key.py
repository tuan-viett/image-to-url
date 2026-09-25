"""API key schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ApiKeyCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    environment: int = Field(default=1, description="1=live, 2=test")


class ApiKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    environment: int
    last_used_at: Optional[datetime]
    created: datetime
    revoked_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApiKeyWithSecretOut(ApiKeyOut):
    """Returned ONLY on creation. `secret` is shown to the user once."""
    secret: str