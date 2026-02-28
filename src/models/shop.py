"""Shop model — core of multi-tenancy."""

from typing import Dict, Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin

DEFAULT_WORKING_HOURS = {
    "mon": {"open": "09:00", "close": "19:00"},
    "tue": {"open": "09:00", "close": "19:00"},
    "wed": {"open": "09:00", "close": "19:00"},
    "thu": {"open": "09:00", "close": "19:00"},
    "fri": {"open": "09:00", "close": "19:00"},
    "sat": {"open": "10:00", "close": "17:00"},
    "sun": None,
}


class Shop(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "shops"

    # Identity
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Telegram
    owner_telegram_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    telegram_bot_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    telegram_bot_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # WhatsApp (Twilio)
    whatsapp_phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Webhook (alternative notification)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Configuration
    greeting_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(5), default="ru")
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    working_hours: Mapped[Dict] = mapped_column(JSONB, default=DEFAULT_WORKING_HOURS)

    # Bot settings
    collect_phone: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_name: Mapped[bool] = mapped_column(Boolean, default=True)
    offer_appointment: Mapped[bool] = mapped_column(Boolean, default=True)

    # Bot personality & customization
    bot_personality: Mapped[Optional[str]] = mapped_column(String(50), default="friendly")
    bot_faq_custom: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    promo_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Plan & limits
    plan: Mapped[str] = mapped_column(String(20), default="free")
    plan_conversations_limit: Mapped[int] = mapped_column(Integer, default=50)

    # Address info for bot responses
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    maps_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    conversations = relationship("Conversation", back_populates="shop", lazy="selectin")
    leads = relationship("Lead", back_populates="shop", lazy="selectin")
    price_rules = relationship("PriceRule", back_populates="shop", lazy="selectin")
