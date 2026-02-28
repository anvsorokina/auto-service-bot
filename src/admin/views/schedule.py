"""Schedule views — appointment management."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.admin.dependencies import get_current_shop
from src.database import get_db
from src.models.lead import Appointment, Lead
from src.models.shop import Shop

logger = structlog.get_logger()

router = APIRouter(prefix="/admin/schedule", tags=["admin-schedule"])

import pathlib

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATUS_LABELS = {
    "pending": "Ожидает",
    "confirmed": "Подтверждена",
    "cancelled": "Отменена",
    "completed": "Завершена",
}

DAYS_RU_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@router.get("", response_class=HTMLResponse)
async def schedule_page(
    request: Request,
    week_offset: int = Query(0),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Weekly schedule view."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    # Calculate week start (Monday)
    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=7)

    # Fetch appointments for the week
    result = await db.execute(
        select(Appointment)
        .options(selectinload(Appointment.lead))
        .where(
            and_(
                Appointment.shop_id == shop.id,
                Appointment.scheduled_at >= datetime.combine(week_start, datetime.min.time()).replace(tzinfo=timezone.utc),
                Appointment.scheduled_at < datetime.combine(week_end, datetime.min.time()).replace(tzinfo=timezone.utc),
            )
        )
        .order_by(Appointment.scheduled_at)
    )
    appointments = result.scalars().all()

    # Group by day
    days = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        day_appointments = [
            a for a in appointments
            if a.scheduled_at.date() == day
        ]
        days.append({
            "date": day,
            "day_name": DAYS_RU_SHORT[i],
            "is_today": day == today,
            "appointments": day_appointments,
        })

    return templates.TemplateResponse("schedule/calendar.html", {
        "request": request,
        "shop": shop,
        "active_page": "schedule",
        "days": days,
        "week_start": week_start,
        "week_end": week_end - timedelta(days=1),
        "week_offset": week_offset,
        "status_labels": STATUS_LABELS,
        "today": today,
    })


@router.patch("/{appointment_id}/status", response_class=HTMLResponse)
async def update_appointment_status(
    request: Request,
    appointment_id: str,
    new_status: str = Form(...),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Update appointment status."""
    if shop is None:
        return HTMLResponse("Unauthorized", status_code=401)

    valid = {"pending", "confirmed", "cancelled", "completed"}
    if new_status not in valid:
        return HTMLResponse("Invalid status", status_code=400)

    await db.execute(
        update(Appointment)
        .where(
            Appointment.id == uuid.UUID(appointment_id),
            Appointment.shop_id == shop.id,
        )
        .values(status=new_status)
    )
    await db.commit()

    label = STATUS_LABELS.get(new_status, new_status)
    return HTMLResponse(
        f'<span class="badge badge-{new_status}">{label}</span>'
    )
