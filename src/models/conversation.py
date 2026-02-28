"""Conversation and Message models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin, TimestampMixin


class Conversation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False
    )

    # Source
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # telegram | whatsapp
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_chat_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Dialog state
    status: Mapped[str] = mapped_column(String(30), default="active")
    current_step: Mapped[str] = mapped_column(String(50), default="greeting")

    # Collected data
    device_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_model: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    problem_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    problem_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    urgency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    has_previous_repair: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    preferred_time: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Estimate
    estimated_price_min: Mapped[Optional[float]] = mapped_column(nullable=True)
    estimated_price_max: Mapped[Optional[float]] = mapped_column(nullable=True)
    price_confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Metrics
    messages_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mode: Mapped[str] = mapped_column(
        String(10), default="bot"
    )  # bot | human

    # Relationships
    shop = relationship("Shop", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", lazy="selectin")


class Message(Base, UUIDMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | bot
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM metadata
    llm_tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    step_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
