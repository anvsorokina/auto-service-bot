"""Conversations views — unified list of all clients (conversations + leads)."""

from __future__ import annotations

import uuid
import pathlib
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.admin.dependencies import get_current_shop
from src.database import get_db
from src.models.conversation import Conversation, Message
from src.models.lead import Lead
from src.models.shop import Shop

logger = structlog.get_logger()

router = APIRouter(prefix="/admin/conversations", tags=["admin-conversations"])

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Steps that map to each warmth level
HOT_STEPS = {"estimate", "contact_info", "completed"}
WARM_STEPS = {"problem", "device_model"}
COLD_STEPS = {"greeting", "device_type"}

CONVERSATION_STATUS_LABELS = {
    "active": "Активный",
    "abandoned": "Брошен",
    "handoff": "Ожидает мастера",
    "human_active": "Мастер отвечает",
    "completed": "Завершён",
}

LEAD_STATUS_LABELS = {
    "pending": "Ожидает",
    "new": "Новая",
    "viewed": "Просмотрена",
    "contacted": "Связались",
    "won": "Закрыта",
    "lost": "Отклонена",
}

DEVICE_CATEGORY_LABELS = {
    "sedan": "Седан",
    "suv": "Внедорожник / Кроссовер",
    "hatchback": "Хэтчбек",
    "minivan": "Минивэн",
    "truck": "Грузовик / Пикап",
    "other": "Другое",
    # legacy keys kept for backwards compatibility
    "smartphone": "Легковой",
    "laptop": "Внедорожник",
    "tablet": "Хэтчбек",
    "watch": "Минивэн",
    "headphones": "Грузовик",
}

STEP_LABELS = {
    "greeting": "Приветствие",
    "device_type": "Тип автомобиля",
    "device_model": "Марка и модель",
    "problem": "Описание проблемы",
    "estimate": "Оценка стоимости",
    "contact_info": "Контакт",
    "appointment": "Запись",
    "completed": "Завершён",
}


def _get_warmth(step: Optional[str]) -> str:
    """Return warmth level string for a conversation step."""
    if step in HOT_STEPS:
        return "hot"
    if step in WARM_STEPS:
        return "warm"
    return "cold"


def _warmth_label(warmth: str) -> str:
    labels = {"hot": "Горячий", "warm": "Тёплый", "cold": "Холодный"}
    return labels.get(warmth, warmth)


async def _get_funnel_stats(db: AsyncSession, shop_id: uuid.UUID) -> dict:
    """Compute mini-funnel statistics for the shop."""
    # Total conversations
    total_result = await db.execute(
        select(func.count()).where(Conversation.shop_id == shop_id)
    )
    total_started = total_result.scalar_one() or 0

    # Reached problem step (step is problem or beyond)
    beyond_problem = list(WARM_STEPS | HOT_STEPS)
    reached_problem_result = await db.execute(
        select(func.count()).where(
            Conversation.shop_id == shop_id,
            Conversation.current_step.in_(beyond_problem),
        )
    )
    reached_problem = reached_problem_result.scalar_one() or 0

    # Became a lead (conversation has a matching lead row)
    became_lead_result = await db.execute(
        select(func.count())
        .select_from(Lead)
        .where(Lead.shop_id == shop_id, Lead.conversation_id.isnot(None))
    )
    became_lead = became_lead_result.scalar_one() or 0

    return {
        "total_started": total_started,
        "reached_problem": reached_problem,
        "became_lead": became_lead,
    }


async def _fetch_conversations(
    db: AsyncSession,
    shop_id: uuid.UUID,
    warmth_filter: Optional[str],
    status_filter: Optional[str],
    search: Optional[str],
    page: int,
    per_page: int,
) -> tuple[list, int]:
    """
    Fetch ALL conversations with optional LEFT JOIN on Lead.

    Returns list of (Conversation, Lead|None) tuples and total count.
    """
    stmt = (
        select(Conversation, Lead)
        .outerjoin(Lead, Lead.conversation_id == Conversation.id)
        .where(Conversation.shop_id == shop_id)
    )

    # Status filter — unified across conversation and lead statuses
    if status_filter:
        if status_filter in ("new", "viewed", "contacted", "won", "lost", "pending"):
            # Lead statuses
            stmt = stmt.where(Lead.status == status_filter)
        else:
            # Conversation statuses (active, abandoned, handoff, human_active, completed)
            stmt = stmt.where(Conversation.status == status_filter)
    else:
        # Default: show all meaningful statuses
        stmt = stmt.where(
            Conversation.status.in_(
                ["active", "abandoned", "handoff", "human_active", "completed"]
            )
        )

    # Warmth filter
    if warmth_filter:
        if warmth_filter == "hot":
            stmt = stmt.where(Conversation.current_step.in_(list(HOT_STEPS)))
        elif warmth_filter == "warm":
            stmt = stmt.where(Conversation.current_step.in_(list(WARM_STEPS)))
        elif warmth_filter == "cold":
            stmt = stmt.where(Conversation.current_step.in_(list(COLD_STEPS)))

    # Search — across both tables
    if search:
        search_like = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(func.coalesce(Lead.customer_name, Conversation.customer_name, "")).like(search_like)
            | func.lower(func.coalesce(Lead.device_full_name, "")).like(search_like)
            | func.lower(func.coalesce(Conversation.device_brand, "")).like(search_like)
            | func.lower(func.coalesce(Conversation.device_model, "")).like(search_like)
            | func.lower(func.coalesce(Lead.problem_summary, Conversation.problem_description, "")).like(search_like)
        )

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one() or 0

    # Order + paginate
    offset = (page - 1) * per_page
    stmt = (
        stmt.order_by(Conversation.last_message_at.desc().nullslast())
        .offset(offset)
        .limit(per_page)
    )

    result = await db.execute(stmt)
    rows = result.all()  # list of (Conversation, Lead|None)

    return rows, total


@router.get("", response_class=HTMLResponse)
async def conversations_list(
    request: Request,
    warmth: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Unified list of all clients — conversations + leads."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    per_page = 20
    funnel_stats = await _get_funnel_stats(db, shop.id)
    rows, total = await _fetch_conversations(
        db, shop.id, warmth, status, search, page, per_page
    )

    # Mark new leads as viewed
    new_lead_ids = [lead.id for conv, lead in rows if lead and lead.status == "new"]
    if new_lead_ids:
        await db.execute(
            update(Lead)
            .where(Lead.id.in_(new_lead_ids))
            .values(status="viewed", updated_at=datetime.now(timezone.utc))
        )
        await db.commit()

    # Attach warmth to each conversation for template use
    for conv, lead in rows:
        conv._warmth = _get_warmth(conv.current_step)

    total_pages = max(1, (total + per_page - 1) // per_page)

    ctx = {
        "request": request,
        "shop": shop,
        "active_page": "conversations",
        "rows": rows,  # list of (Conversation, Lead|None)
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "warmth_filter": warmth,
        "status_filter": status,
        "search": search or "",
        "funnel": funnel_stats,
        "status_labels": CONVERSATION_STATUS_LABELS,
        "lead_status_labels": LEAD_STATUS_LABELS,
        "device_category_labels": DEVICE_CATEGORY_LABELS,
        "step_labels": STEP_LABELS,
        "warmth_label": _warmth_label,
    }

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            "conversations/partials/table.html", ctx
        )

    return templates.TemplateResponse("conversations/list.html", ctx)


@router.get("/{conversation_id}", response_class=HTMLResponse)
async def conversation_detail(
    request: Request,
    conversation_id: str,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Conversation detail — full chat history + collected data."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        return RedirectResponse(url="/admin/conversations")

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.shop_id == shop.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        return RedirectResponse(url="/admin/conversations")

    # Fetch messages
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv_uuid)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    # Check if a lead exists for this conversation
    lead_result = await db.execute(
        select(Lead).where(Lead.conversation_id == conv_uuid)
    )
    lead = lead_result.scalar_one_or_none()

    warmth = _get_warmth(conversation.current_step)

    return templates.TemplateResponse(
        "conversations/detail.html",
        {
            "request": request,
            "shop": shop,
            "active_page": "conversations",
            "conversation": conversation,
            "chat_messages": messages,
            "lead": lead,
            "warmth": warmth,
            "warmth_label": _warmth_label(warmth),
            "status_labels": CONVERSATION_STATUS_LABELS,
            "lead_status_labels": LEAD_STATUS_LABELS,
            "device_category_labels": DEVICE_CATEGORY_LABELS,
            "step_labels": STEP_LABELS,
        },
    )
