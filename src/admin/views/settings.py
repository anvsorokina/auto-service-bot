"""Settings views — shop and bot configuration."""

from __future__ import annotations

import json
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_shop
from src.database import get_db
from src.models.shop import Shop

logger = structlog.get_logger()

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])

import pathlib

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

PERSONALITY_OPTIONS = [
    ("friendly", "Дружелюбный", "Тёплый и неформальный стиль. Эмодзи, шутки, эмпатия."),
    ("professional", "Профессиональный", "Вежливый и деловой. Без лишних эмоций."),
    ("casual", "Разговорный", "Максимально простой и неформальный стиль."),
]

DAYS_RU = {
    "mon": "Понедельник",
    "tue": "Вторник",
    "wed": "Среда",
    "thu": "Четверг",
    "fri": "Пятница",
    "sat": "Суббота",
    "sun": "Воскресенье",
}


@router.get("", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    saved: Optional[str] = None,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Shop and bot settings page."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    return templates.TemplateResponse("settings/index.html", {
        "request": request,
        "shop": shop,
        "active_page": "settings",
        "personality_options": PERSONALITY_OPTIONS,
        "days_ru": DAYS_RU,
        "saved": saved,
    })


@router.post("", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    # Basic info
    name: str = Form(...),
    address: str = Form(""),
    maps_url: str = Form(""),
    # Bot settings
    greeting_text: str = Form(""),
    bot_personality: str = Form("friendly"),
    promo_text: str = Form(""),
    bot_faq_custom: str = Form(""),
    collect_phone: bool = Form(False),
    collect_name: bool = Form(False),
    offer_appointment: bool = Form(False),
    # Working hours (JSON string from form)
    working_hours_json: str = Form("{}"),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Save shop settings."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    # Parse working hours
    try:
        working_hours = json.loads(working_hours_json) if working_hours_json else shop.working_hours
    except json.JSONDecodeError:
        working_hours = shop.working_hours

    values = {
        "name": name.strip(),
        "address": address.strip() or None,
        "maps_url": maps_url.strip() or None,
        "greeting_text": greeting_text.strip() or None,
        "bot_personality": bot_personality,
        "promo_text": promo_text.strip() or None,
        "bot_faq_custom": bot_faq_custom.strip() or None,
        "collect_phone": collect_phone,
        "collect_name": collect_name,
        "offer_appointment": offer_appointment,
        "working_hours": working_hours,
    }

    await db.execute(
        update(Shop).where(Shop.id == shop.id).values(**values)
    )
    await db.commit()

    logger.info("shop_settings_saved", shop_id=str(shop.id))
    return RedirectResponse(url="/admin/settings?saved=1", status_code=303)
