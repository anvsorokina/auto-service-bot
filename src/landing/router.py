"""Landing page and demo request routes."""

import pathlib

import structlog
from aiogram import Bot
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db
from src.models.demo_request import DemoRequest

logger = structlog.get_logger()

router = APIRouter()

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class DemoRequestIn(BaseModel):
    name: str
    shop_name: str
    contact: str
    country: str = "ru"


DEMO_NOTIFICATION_TEMPLATE = """🚀 <b>Новая заявка на демо!</b>

👤 <b>Имя:</b> {name}
🏪 <b>Сервис:</b> {shop_name}
📞 <b>Контакт:</b> {contact}
🌍 <b>Страна:</b> {country}"""

COUNTRY_NAMES = {
    "ru": "Россия",
    "kz": "Казахстан",
    "uz": "Узбекистан",
    "ge": "Грузия",
    "other": "Другая",
}


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Serve the landing page."""
    return templates.TemplateResponse("index.html", {"request": request})


@router.post("/api/demo-request")
async def create_demo_request(
    data: DemoRequestIn,
    db: AsyncSession = Depends(get_db),
):
    """Save demo request to DB and send Telegram notification."""
    demo_req = DemoRequest(
        name=data.name,
        shop_name=data.shop_name,
        contact=data.contact,
        country=data.country,
    )
    db.add(demo_req)
    await db.flush()

    logger.info(
        "demo_request_created",
        id=str(demo_req.id),
        name=data.name,
        shop_name=data.shop_name,
        country=data.country,
    )

    # Send Telegram notification to platform owner
    if settings.demo_notify_telegram_bot_token and settings.demo_notify_telegram_chat_id:
        try:
            bot = Bot(token=settings.demo_notify_telegram_bot_token)
            text = DEMO_NOTIFICATION_TEMPLATE.format(
                name=data.name,
                shop_name=data.shop_name,
                contact=data.contact,
                country=COUNTRY_NAMES.get(data.country, data.country),
            )
            await bot.send_message(
                chat_id=int(settings.demo_notify_telegram_chat_id),
                text=text,
                parse_mode="HTML",
            )
            await bot.session.close()
            logger.info("demo_notification_sent", chat_id=settings.demo_notify_telegram_chat_id)
        except Exception as e:
            logger.error("demo_notification_failed", error=str(e))

    return {"status": "ok", "id": str(demo_req.id)}
