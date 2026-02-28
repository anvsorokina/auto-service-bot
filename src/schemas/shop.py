"""Shop schemas for API."""

from pydantic import BaseModel
from typing import Optional


class ShopCreate(BaseModel):
    slug: str
    name: str
    telegram_bot_token: str
    owner_telegram_id: int
    language: str = "ru"
    currency: str = "RUB"
    timezone: str = "Europe/Moscow"
    greeting_text: Optional[str] = None
    address: Optional[str] = None
    maps_url: Optional[str] = None


class ShopResponse(BaseModel):
    id: str
    slug: str
    name: str
    telegram_bot_username: Optional[str] = None
    language: str
    currency: str
    is_active: bool

    model_config = {"from_attributes": True}
