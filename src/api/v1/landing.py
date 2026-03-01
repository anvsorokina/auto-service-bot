"""Landing page demo request endpoint — sends leads to Telegram."""

import time
from collections import defaultdict

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.config import settings

logger = structlog.get_logger()
router = APIRouter(prefix="/api/landing", tags=["landing"])

# Simple per-IP rate limit: 1 request per 60 seconds
_last_request: dict[str, float] = defaultdict(float)
_COOLDOWN = 60

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


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
    "kg": "Кыргызстан",
    "am": "Армения",
    "other": "Другая страна",
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

    token = settings.landing_tg_bot_token
    chat_id = settings.landing_tg_chat_id

    if not token or not chat_id:
        logger.error(
            "landing_telegram_not_configured",
            has_token=bool(token),
            has_chat_id=bool(chat_id),
        )
        raise HTTPException(status_code=500, detail="Не удалось отправить заявку")

    country = COUNTRY_NAMES.get(body.country, body.country)
    text = (
        "🔔 <b>Новая заявка с лендинга</b>\n\n"
        f"👤 <b>Имя:</b> {body.name}\n"
        f"🏪 <b>Сервис:</b> {body.shop_name}\n"
        f"📱 <b>Контакт:</b> {body.contact}\n"
        f"🌍 <b>Страна:</b> {country}\n"
    )

    url = _TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                raise ValueError(f"Telegram API error: {result}")
    except Exception as e:
        logger.error("landing_telegram_send_error", error=str(e), url=url, chat_id=chat_id)
        raise HTTPException(status_code=500, detail="Не удалось отправить заявку") from e

    logger.info("landing_demo_request", name=body.name, shop=body.shop_name, country=body.country)
    return {"ok": True}
