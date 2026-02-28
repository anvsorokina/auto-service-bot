"""Leads API — for the shop owner dashboard."""

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.lead import Lead

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["leads"])


@router.get("/leads")
async def list_leads(
    shop_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List leads for a shop.

    Args:
        shop_id: UUID of the shop
        status: Optional status filter (pending, new, viewed, contacted, won, lost)
        limit: Max results
        offset: Pagination offset
        db: Database session

    Returns:
        {"leads": [...], "total": int}
    """
    stmt = select(Lead).where(Lead.shop_id == shop_id)

    if status:
        stmt = stmt.where(Lead.status == status)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Fetch page
    stmt = stmt.order_by(Lead.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    leads = result.scalars().all()

    return {
        "leads": [
            {
                "id": str(lead.id),
                "customer_name": lead.customer_name,
                "customer_phone": lead.customer_phone,
                "device_category": lead.device_category,
                "device_full_name": lead.device_full_name,
                "problem_summary": lead.problem_summary,
                "urgency": lead.urgency,
                "estimated_price_min": float(lead.estimated_price_min) if lead.estimated_price_min else None,
                "estimated_price_max": float(lead.estimated_price_max) if lead.estimated_price_max else None,
                "status": lead.status,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
            }
            for lead in leads
        ],
        "total": total,
    }
