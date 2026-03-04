"""InBuild conversation schemas — construction/renovation vertical."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class BuildStep(str, Enum):
    """FSM steps for construction intake dialog.

    Flow: greeting -> service_type -> property_info -> project_desc ->
          timeline_budget -> estimate -> contact_info -> completed
    """

    GREETING = "greeting"
    SERVICE_TYPE = "service_type"
    PROPERTY_INFO = "property_info"
    PROJECT_DESCRIPTION = "project_desc"
    TIMELINE_BUDGET = "timeline_budget"
    ESTIMATE = "estimate"
    CONTACT_INFO = "contact_info"
    COMPLETED = "completed"


class BuildCollectedData(BaseModel):
    """Data collected during construction intake conversation."""

    # Service
    service_category: Optional[str] = None
    service_description: Optional[str] = None

    # Property
    property_type: Optional[str] = None
    property_area_sqm: Optional[float] = None
    property_address: Optional[str] = None
    property_condition: Optional[str] = None

    # Project details
    project_description: Optional[str] = None
    has_design_project: Optional[bool] = None
    scope: Optional[str] = None

    # Timeline & budget
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    budget_currency: str = "USD"
    timeline: Optional[str] = None
    preferred_start_date: Optional[str] = None

    # Customer
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_company: Optional[str] = None

    # Estimate
    estimated_price_min: Optional[float] = None
    estimated_price_max: Optional[float] = None
    estimated_duration_days: Optional[int] = None
    price_confidence: Optional[str] = None

    # Decision
    preferred_time: Optional[str] = None


class BuildSessionState(BaseModel):
    """Full session state for construction conversations, persisted in Redis."""

    conversation_id: str
    shop_id: str
    current_step: BuildStep = BuildStep.GREETING
    collected: BuildCollectedData = BuildCollectedData()
    retry_count: int = 0
    language: str = "ru"
    messages_count: int = 0
    message_history: list = []
    lead_id: Optional[str] = None
    channel: str = "telegram"
