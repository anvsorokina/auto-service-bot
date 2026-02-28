"""Conversation state schemas stored in Redis."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ConversationStep(str, Enum):
    """FSM steps for the intake dialog.

    Order: greeting → device → problem → estimate → appointment → contact → done.
    Estimate is shown BEFORE contact_info so the customer knows the price
    and agrees to come in before we ask for personal details.
    """

    GREETING = "greeting"
    DEVICE_TYPE = "device_type"
    DEVICE_MODEL = "device_model"
    PROBLEM = "problem"
    PREVIOUS_REPAIR = "previous_repair"
    URGENCY = "urgency"
    ESTIMATE = "estimate"
    APPOINTMENT = "appointment"
    CONTACT_INFO = "contact_info"
    COMPLETED = "completed"


class CollectedData(BaseModel):
    """Data collected during conversation."""

    # Device
    device_category: Optional[str] = None
    device_brand: Optional[str] = None
    device_model: Optional[str] = None

    # Problem
    problem_raw: Optional[str] = None
    problem_category: Optional[str] = None
    problem_description: Optional[str] = None

    # Context
    urgency: Optional[str] = None
    has_previous_repair: Optional[bool] = None

    # Customer
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None

    # Estimate
    estimated_price_min: Optional[float] = None
    estimated_price_max: Optional[float] = None
    price_confidence: Optional[str] = None

    # Appointment
    preferred_time: Optional[str] = None
    selected_tier: Optional[str] = None


class SessionState(BaseModel):
    """Full session state persisted in Redis."""

    conversation_id: str
    shop_id: str
    current_step: ConversationStep = ConversationStep.GREETING
    collected: CollectedData = CollectedData()
    retry_count: int = 0
    language: str = "ru"
    messages_count: int = 0
    message_history: list[dict] = []  # [{"role": "user"/"bot", "text": "..."}]
    lead_id: Optional[str] = None  # UUID of lead created at ESTIMATE step
    channel: str = "telegram"  # telegram | whatsapp
