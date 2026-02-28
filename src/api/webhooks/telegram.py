"""Telegram webhook endpoint — receives updates from Telegram Bot API."""

import structlog
from aiogram import Bot
from aiogram.types import Update
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.factory import get_or_create_bot
from src.bot.handlers.message import handle_callback, handle_message
from src.bot.middleware import get_shop_by_token
from src.conversation.engine import ConversationEngine
from src.conversation.session import SessionManager
from src.database import get_db
from src.redis_client import get_redis

logger = structlog.get_logger()

router = APIRouter()

# TODO: remove after testing — restrict bot to owner only
ALLOWED_TELEGRAM_IDS: set[int] = {75524586, 171054416}


@router.post("/webhook/telegram/{shop_token}")
async def telegram_webhook(
    shop_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive Telegram webhook update for a specific shop.

    Each shop has its own bot token. The token in the URL is used
    to identify which shop this update belongs to.

    Args:
        shop_token: The shop's Telegram bot token (from URL path)
        request: FastAPI request object
        db: Database session

    Returns:
        {"ok": True} on success
    """
    # 1. Resolve shop from token
    shop = await get_shop_by_token(db, shop_token)
    if not shop:
        logger.warning("webhook_unknown_shop", token_prefix=shop_token[:10])
        raise HTTPException(status_code=404, detail="Shop not found")

    # 2. Parse the Telegram update
    try:
        body = await request.json()
        bot = await get_or_create_bot(shop_token)
        update = Update.model_validate(body, context={"bot": bot})
    except Exception as e:
        logger.error("webhook_parse_error", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid update")

    # 2.5 Testing whitelist — ignore messages from other users
    user = None
    if update.message and update.message.from_user:
        user = update.message.from_user
    elif update.callback_query and update.callback_query.from_user:
        user = update.callback_query.from_user

    if ALLOWED_TELEGRAM_IDS and user and user.id not in ALLOWED_TELEGRAM_IDS:
        logger.debug("user_not_in_whitelist", user_id=user.id)
        return {"ok": True}

    # 3. Create engine with shop settings for LLM personalization
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

    # 4. Route to handler
    shop_id = str(shop.id)

    if update.message:
        await handle_message(
            message=update.message,
            bot=bot,
            engine=engine,
            shop_id=shop_id,
        )
    elif update.callback_query:
        await handle_callback(
            callback=update.callback_query,
            bot=bot,
            engine=engine,
            shop_id=shop_id,
        )

    return {"ok": True}
