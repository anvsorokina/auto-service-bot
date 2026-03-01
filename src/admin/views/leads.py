"""Leads views — list, detail, status updates, notes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.admin.dependencies import get_current_shop
from src.database import get_db
from src.models.conversation import Conversation, Message
from src.models.lead import Lead
from src.models.shop import Shop

logger = structlog.get_logger()

router = APIRouter(prefix="/admin/leads", tags=["admin-leads"])

import pathlib

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATUS_LABELS = {
    "pending": "Ожидает",
    "new": "Новая",
    "viewed": "Просмотрена",
    "contacted": "Связались",
    "won": "Закрыта",
    "lost": "Отклонена",
}

URGENCY_LABELS = {
    "urgent": "Срочно",
    "normal": "Обычная",
    "low": "Не срочно",
}

DEVICE_CATEGORY_LABELS = {
    "sedan": "🚗 Седан",
    "suv": "🚙 Внедорожник / Кроссовер",
    "hatchback": "🚗 Хэтчбек",
    "minivan": "🚐 Минивэн",
    "truck": "🚛 Грузовик / Пикап",
    "commercial": "🚚 Коммерческий",
    "other": "🔧 Другое",
}


@router.get("", response_class=HTMLResponse)
async def leads_list(
    request: Request,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Redirect to unified clients page."""
    return RedirectResponse(url="/admin/conversations")


@router.get("/{lead_id}", response_class=HTMLResponse)
async def lead_detail(
    request: Request,
    lead_id: str,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Lead detail page with conversation history."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    # Fetch lead
    result = await db.execute(
        select(Lead).where(Lead.id == uuid.UUID(lead_id), Lead.shop_id == shop.id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        return RedirectResponse(url="/admin/leads")

    # Fetch conversation + messages
    messages = []
    conversation = None
    if lead.conversation_id:
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == lead.conversation_id)
        )
        conversation = conv_result.scalar_one_or_none()

        msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == lead.conversation_id)
            .order_by(Message.created_at.asc())
        )
        messages = msg_result.scalars().all()

    return templates.TemplateResponse("leads/detail.html", {
        "request": request,
        "shop": shop,
        "active_page": "leads",
        "lead": lead,
        "conversation": conversation,
        "chat_messages": messages,
        "status_labels": STATUS_LABELS,
        "urgency_labels": URGENCY_LABELS,
        "device_category_labels": DEVICE_CATEGORY_LABELS,
    })


@router.patch("/{lead_id}/status", response_class=HTMLResponse)
async def update_lead_status(
    request: Request,
    lead_id: str,
    new_status: str = Form(...),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Update lead status (HTMX partial)."""
    if shop is None:
        return HTMLResponse("Unauthorized", status_code=401)

    valid_statuses = {"pending", "new", "viewed", "contacted", "won", "lost"}
    if new_status not in valid_statuses:
        return HTMLResponse("Invalid status", status_code=400)

    await db.execute(
        update(Lead)
        .where(Lead.id == uuid.UUID(lead_id), Lead.shop_id == shop.id)
        .values(status=new_status, updated_at=datetime.now(timezone.utc))
    )
    await db.commit()

    logger.info("lead_status_updated", lead_id=lead_id, new_status=new_status)

    # Return updated badge
    label = STATUS_LABELS.get(new_status, new_status)
    return HTMLResponse(
        f'<span class="badge badge-{new_status}">{label}</span>'
    )


@router.patch("/{lead_id}/notes", response_class=HTMLResponse)
async def update_lead_notes(
    request: Request,
    lead_id: str,
    master_notes: str = Form(""),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Update lead master notes (HTMX partial)."""
    if shop is None:
        return HTMLResponse("Unauthorized", status_code=401)

    await db.execute(
        update(Lead)
        .where(Lead.id == uuid.UUID(lead_id), Lead.shop_id == shop.id)
        .values(master_notes=master_notes, updated_at=datetime.now(timezone.utc))
    )
    await db.commit()

    return HTMLResponse(
        '<div class="alert alert-success">Заметка сохранена</div>'
    )
