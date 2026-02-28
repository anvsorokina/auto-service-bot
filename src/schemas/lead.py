"""Lead schemas for notifications and API."""

from pydantic import BaseModel
from typing import Optional


class LeadNotification(BaseModel):
    """Data for lead notification to shop owner."""

    lead_id: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_telegram: Optional[str] = None
    device_full_name: Optional[str] = None
    problem_summary: Optional[str] = None
    urgency: Optional[str] = None
    estimated_price_min: Optional[float] = None
    estimated_price_max: Optional[float] = None
    preferred_time: Optional[str] = None
    created_at: Optional[str] = None
    priority: str = "standard"  # urgent | standard | info
    messages_count: int = 0
    session_duration: Optional[str] = None


class PriceEstimate(BaseModel):
    """Result from pricing engine."""

    tiers: list["PriceTier"] = []
    confidence: str = "none"  # high | medium | low | none
    message: Optional[str] = None
    duration_minutes: Optional[int] = None


class PriceTier(BaseModel):
    """Single price tier (basic / improved / original)."""

    tier: str  # basic | improved | original
    label_ru: str
    label_en: str
    price_min: float
    price_max: float
    warranty_months: int = 3
    description: Optional[str] = None
