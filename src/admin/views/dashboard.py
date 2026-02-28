"""Dashboard views — analytics and stats."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_shop
from src.database import get_db
from src.models.conversation import Conversation, Message
from src.models.lead import Appointment, Lead
from src.models.shop import Shop

logger = structlog.get_logger()

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])

import pathlib

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Main dashboard with stats."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Leads stats
    leads_total = (await db.execute(
        select(func.count()).select_from(Lead).where(Lead.shop_id == shop.id)
    )).scalar_one()

    leads_today = (await db.execute(
        select(func.count()).select_from(Lead).where(
            Lead.shop_id == shop.id,
            Lead.created_at >= today_start,
        )
    )).scalar_one()

    leads_this_month = (await db.execute(
        select(func.count()).select_from(Lead).where(
            Lead.shop_id == shop.id,
            Lead.created_at >= month_start,
        )
    )).scalar_one()

    leads_new = (await db.execute(
        select(func.count()).select_from(Lead).where(
            Lead.shop_id == shop.id,
            Lead.status.in_(["new", "viewed"]),
        )
    )).scalar_one()

    leads_won = (await db.execute(
        select(func.count()).select_from(Lead).where(
            Lead.shop_id == shop.id,
            Lead.status == "won",
        )
    )).scalar_one()

    # Conversion rate
    conversion = (leads_won / leads_total * 100) if leads_total > 0 else 0

    # Appointments today
    appointments_today = (await db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.shop_id == shop.id,
            Appointment.scheduled_at >= today_start,
            Appointment.scheduled_at < today_start + timedelta(days=1),
            Appointment.status.in_(["pending", "confirmed"]),
        )
    )).scalar_one()

    # Token usage this month
    tokens_month = (await db.execute(
        select(func.coalesce(func.sum(Message.llm_tokens_used), 0))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.shop_id == shop.id,
            Message.created_at >= month_start,
        )
    )).scalar_one()

    # Conversations this month
    conversations_month = (await db.execute(
        select(func.count()).select_from(Conversation).where(
            Conversation.shop_id == shop.id,
            Conversation.created_at >= month_start,
        )
    )).scalar_one()

    # Estimated token cost (Sonnet 4: ~$3/1M input + $15/1M output, average ~$9/1M)
    estimated_cost_usd = tokens_month / 1_000_000 * 9
    estimated_cost_rub = estimated_cost_usd * 90  # approximate rate

    # Status breakdown
    status_counts = {}
    status_result = await db.execute(
        select(Lead.status, func.count())
        .where(Lead.shop_id == shop.id)
        .group_by(Lead.status)
    )
    for status, count in status_result:
        status_counts[status] = count

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "shop": shop,
        "active_page": "dashboard",
        "leads_total": leads_total,
        "leads_today": leads_today,
        "leads_this_month": leads_this_month,
        "leads_new": leads_new,
        "leads_won": leads_won,
        "conversion": conversion,
        "appointments_today": appointments_today,
        "tokens_month": tokens_month,
        "conversations_month": conversations_month,
        "estimated_cost_rub": estimated_cost_rub,
        "status_counts": status_counts,
    })
