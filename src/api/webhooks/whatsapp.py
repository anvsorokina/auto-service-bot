"""WhatsApp (Twilio) webhook endpoint — receives incoming WhatsApp messages."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.conversation.engine import ConversationEngine
from src.conversation.session import SessionManager
from src.database import get_db
from src.models.shop import Shop
from src.redis_client import get_redis
from src.whatsapp.client import get_whatsapp_client
from src.whatsapp.keyboard_adapter import (
    clear_menu,
    keyboard_to_text,
    resolve_menu_choice,
    save_menu,
)

logger = structlog.get_logger()

router = APIRouter()


async def _resolve_shop(db: AsyncSession, to_number: str) -> Shop | None:
    """Find shop by WhatsApp phone number.

    For sandbox testing, if no shop has whatsapp_phone_number set,
    fall back to the first active shop (single-tenant mode).
    """
    # Try exact match on whatsapp_phone_number
    result = await db.execute(
        select(Shop).where(
            Shop.whatsapp_phone_number == to_number,
            Shop.is_active == True,  # noqa: E712
        )
    )
    shop = result.scalar_one_or_none()
    if shop:
        return shop

    # Sandbox fallback: use first active shop
    result = await db.execute(
        select(Shop).where(Shop.is_active == True).limit(1)  # noqa: E712
    )
    shop = result.scalar_one_or_none()
    if shop:
        logger.info("whatsapp_sandbox_fallback", shop_id=str(shop.id))
    return shop


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Receive incoming WhatsApp message from Twilio.

    Twilio sends application/x-www-form-urlencoded with fields:
      - From: "whatsapp:+79123456789"
      - To: "whatsapp:+14155238886"
      - Body: message text
      - MessageSid, NumMedia, etc.

    Returns empty 200 OK (Twilio doesn't use the response body).
    """
    form = await request.form()

    from_raw = form.get("From", "")
    to_raw = form.get("To", "")
    body = form.get("Body", "")
    message_sid = form.get("MessageSid", "")

    # Strip "whatsapp:" prefix
    user_phone = from_raw.replace("whatsapp:", "").strip()
    to_number = to_raw.replace("whatsapp:", "").strip()

    if not user_phone or not body:
        logger.warning("whatsapp_empty_message", from_raw=from_raw)
        return Response(status_code=200)

    logger.info(
        "whatsapp_message_received",
        user_phone=user_phone,
        to_number=to_number,
        text_preview=body[:50],
        message_sid=message_sid,
    )

    # 1. Resolve shop
    shop = await _resolve_shop(db, to_number)
    if not shop:
        logger.warning("whatsapp_no_shop", to_number=to_number)
        return Response(status_code=200)

    shop_id = str(shop.id)

    # 2. Build engine
    redis = await get_redis()
    session_manager = SessionManager(redis)

    shop_config = {
        "bot_personality": getattr(shop, "bot_personality", None) or "friendly",
        "greeting_text": getattr(shop, "greeting_text", None),
        "promo_text": getattr(shop, "promo_text", None),
        "bot_faq_custom": getattr(shop, "bot_faq_custom", None),
        "address": getattr(shop, "address", None),
        "shop_name": getattr(shop, "name", None),
    }

    engine = ConversationEngine(session_manager, shop_config=shop_config, db=db)

    # 3. Check if user input matches a menu choice (keyboard selection)
    callback_data = await resolve_menu_choice(redis, shop_id, user_phone, body)

    if callback_data:
        # User selected a menu option → route to callback handler
        await clear_menu(redis, shop_id, user_phone)
        result = await engine.handle_callback(
            shop_id=shop_id,
            user_id=user_phone,
            callback_data=callback_data,
        )
    else:
        # Regular text message
        result = await engine.handle_message(
            shop_id=shop_id,
            user_id=user_phone,
            message_text=body,
            channel="whatsapp",
        )

    # 4. Send response via Twilio
    if result.response_text:
        wa_client = get_whatsapp_client()
        if wa_client:
            response_text = result.response_text

            # If there's a keyboard, convert to numbered list and save mapping
            if result.keyboard:
                menu_text, mapping = keyboard_to_text(result.keyboard)
                response_text = f"{response_text}\n\n{menu_text}"
                await save_menu(redis, shop_id, user_phone, mapping)

            try:
                await wa_client.send_message(user_phone, response_text)
            except Exception as e:
                logger.error(
                    "whatsapp_send_error",
                    error=str(e),
                    user_phone=user_phone,
                    shop_id=shop_id,
                )
        else:
            logger.warning("whatsapp_client_not_configured", shop_id=shop_id)

    return Response(status_code=200)
