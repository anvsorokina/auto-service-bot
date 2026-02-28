"""Lead repository — creates and manages leads."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.lead import Lead
from src.schemas.conversation import SessionState

logger = structlog.get_logger()


class LeadRepository:
    """Manages lead creation and updates."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_from_session(
        self,
        state: SessionState,
        customer_telegram: str | None = None,
    ) -> Lead:
        """Create a new lead from completed conversation session.

        Args:
            state: The final session state with all collected data
            customer_telegram: Customer's Telegram username

        Returns:
            Created Lead object
        """
        collected = state.collected

        device_parts = [
            collected.device_brand or "",
            collected.device_model or "",
        ]
        device_full_name = " ".join(p for p in device_parts if p).strip() or None

        lead = Lead(
            shop_id=uuid.UUID(state.shop_id),
            conversation_id=uuid.UUID(state.conversation_id),
            customer_name=collected.customer_name,
            customer_phone=collected.customer_phone,
            customer_telegram=customer_telegram,
            device_full_name=device_full_name,
            problem_summary=collected.problem_description or collected.problem_category,
            urgency=collected.urgency or "normal",
            estimated_price_min=collected.estimated_price_min,
            estimated_price_max=collected.estimated_price_max,
            status="new",
        )

        self.db.add(lead)
        await self.db.flush()

        logger.info(
            "lead_created",
            lead_id=str(lead.id),
            shop_id=state.shop_id,
            device=device_full_name,
            urgency=lead.urgency,
        )

        return lead

    async def update_status(self, lead_id: str, status: str) -> None:
        """Update lead status."""
        from sqlalchemy import update

        stmt = (
            update(Lead)
            .where(Lead.id == uuid.UUID(lead_id))
            .values(status=status, updated_at=datetime.now(timezone.utc))
        )
        await self.db.execute(stmt)
