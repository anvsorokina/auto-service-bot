"""Demo request model — stores landing page form submissions."""

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin, TimestampMixin


class DemoRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "demo_requests"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    shop_name: Mapped[str] = mapped_column(String(300), nullable=False)
    contact: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(10), default="ru")
    status: Mapped[str] = mapped_column(String(30), default="new")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
