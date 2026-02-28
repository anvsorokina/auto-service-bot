"""Device categories and repair types — global reference data."""

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin


class DeviceCategory(Base, UUIDMixin):
    __tablename__ = "device_categories"

    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    repair_types = relationship("RepairType", back_populates="device_category")


class RepairType(Base, UUIDMixin):
    __tablename__ = "repair_types"

    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name_ru: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    device_category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("device_categories.id"), nullable=True
    )
    typical_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    requires_part: Mapped[bool] = mapped_column(Boolean, default=True)

    device_category = relationship("DeviceCategory", back_populates="repair_types")
