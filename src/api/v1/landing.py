"""Landing page demo request endpoint — sends leads to Telegram."""

import time
from collections import defaultdict

import structlog
from aiogram import Bot
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.config import settings

logger = structlog.get_logger()
router = APIRouter(prefix="/api/landing", tags=["landing"])

# Simple per-IP rate limit: 1 request per 60 seconds
_last_request: dict[str, float] = defaultdict(float)
_COOLDOWN = 60


class DemoRequest(BaseModel):
    name: str
    shop_name: str
    contact: str
    country: str = "ru"


COUNTRY_NAMES = {
    "ru": "Россия",
    "kz": "Казахстан",
    "uz": "Узбекистан",
    "ge": "Грузия",
    "other": "Другая",
}


@router.post("/demo-request")
async def submit_demo_request(body: DemoRequest, request: Request):
    """Accept demo request from landing page and send to Telegram."""
    # Rate limit by IP
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    if now - _last_request[ip] < _COOLDOWN:
        raise HTTPException(status_code=429, detail="Подождите минуту перед повторной отправкой")
    _last_request[ip] = now

    country = COUNTRY_NAMES.get(body.country, body.country)
    text = (
        "🔔 <b>Новая заявка с лендинга</b>\n\n"
        f"👤 <b>Имя:</b> {body.name}\n"
        f"🏪 <b>Сервис:</b> {body.shop_name}\n"
        f"📱 <b>Контакт:</b> {body.contact}\n"
        f"🌍 <b>Страна:</b> {country}\n"
    )

    try:
        bot = Bot(token=settings.landing_tg_bot_token)
        try:
            await bot.send_message(
                chat_id=settings.landing_tg_chat_id,
                text=text,
                parse_mode="HTML",
            )
        finally:
            await bot.session.close()
    except Exception as e:
        logger.error("landing_telegram_send_error", error=str(e))
        raise HTTPException(status_code=500, detail="Не удалось отправить заявку") from e

    logger.info("landing_demo_request", name=body.name, shop=body.shop_name, country=body.country)
    return {"ok": True}
