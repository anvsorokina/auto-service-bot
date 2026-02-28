"""Lead and Appointment models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin, TimestampMixin


class Lead(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "leads"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False
    )
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), unique=True, nullable=True
    )

    # Customer info (denormalized)
    customer_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    customer_telegram: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Device & problem
    device_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_full_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    problem_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    urgency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Price
    estimated_price_min: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    estimated_price_max: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Processing status
    status: Mapped[str] = mapped_column(String(30), default="new")  # new|viewed|contacted|won|lost
    master_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notification
    notification_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    shop = relationship("Shop", back_populates="leads")
    appointment = relationship("Appointment", back_populates="lead", uselist=False)


class Appointment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "appointments"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False
    )
    lead_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=True
    )

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending|confirmed|cancelled|completed

    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    lead = relationship("Lead", back_populates="appointment")
