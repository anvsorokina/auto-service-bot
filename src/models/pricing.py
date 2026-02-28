"""Price rules — per-shop pricing with priority matching."""

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin, TimestampMixin


class PriceRule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "price_rules"

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    repair_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repair_types.id"), nullable=True
    )

    # Filters (NULL = any)
    device_brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_model_pattern: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Price range
    price_min: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_max: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Tier info (basic / improved / original)
    tier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tier_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warranty_months: Mapped[int] = mapped_column(Integer, default=3)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    shop = relationship("Shop", back_populates="price_rules")
