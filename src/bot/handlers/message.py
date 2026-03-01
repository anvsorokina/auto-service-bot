"""Main message handler — routes all incoming messages through ConversationEngine."""

import structlog
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from typing import Optional

from src.conversation.engine import ConversationEngine
from src.conversation.steps.base import StepResult
from src.redis_client import get_redis

logger = structlog.get_logger()

# Demo message limit for non-owner users
DEMO_MESSAGE_LIMIT = 5
DAILY_NEW_USERS_LIMIT = 100
DEMO_LIMIT_TEXT = (
    "Для тестирования доступно только пять сообщений. "
    "Запишись на демо нашей CRM и мы покажем тебе как легко настраивается бот!"
)
DAILY_LIMIT_TEXT = (
    "К сожалению, сейчас бот перегружен. "
    "Попробуйте позже или запишитесь на демо — мы покажем всё лично!"
)


async def _check_daily_new_users_limit(user_id: str, owner_telegram_id: Optional[int]) -> bool:
    """Check if we've exceeded the daily new users cap (anti-abuse).

    Returns True if the user is allowed, False if blocked.
    Already-seen users and the owner are always allowed.
    """
    if owner_telegram_id and str(owner_telegram_id) == user_id:
        return True

    redis = await get_redis()

    # If this user already has a message counter, they're not new — allow
    existing = await redis.exists(f"demo_msg_count:{user_id}")
    if existing:
        return True

    # Check daily new users counter
    from datetime import date
    daily_key = f"demo_daily_new_users:{date.today().isoformat()}"
    count = await redis.get(daily_key)

    if count is not None and int(count) >= DAILY_NEW_USERS_LIMIT:
        logger.warning("daily_new_users_limit_reached", user_id=user_id, count=int(count))
        return False

    return True


async def _increment_daily_new_users(user_id: str, owner_telegram_id: Optional[int]) -> None:
    """Register a new user in the daily counter (called once per new user)."""
    if owner_telegram_id and str(owner_telegram_id) == user_id:
        return

    redis = await get_redis()

    # Only increment if this is a truly new user (no existing counter)
    existing = await redis.exists(f"demo_msg_count:{user_id}")
    if existing:
        return

    from datetime import date
    daily_key = f"demo_daily_new_users:{date.today().isoformat()}"
    pipe = redis.pipeline()
    pipe.incr(daily_key)
    pipe.expire(daily_key, 86400 * 2)  # Expire after 2 days (safety margin)
    await pipe.execute()


async def _check_demo_limit(
    user_id: str,
    owner_telegram_id: Optional[int],
) -> bool:
    """Check if the user has exceeded the demo message limit.

    Returns True if the user is allowed to send messages, False if blocked.
    Owner (owner_telegram_id) always gets unlimited access.
    """
    # Owner always has unlimited access
    if owner_telegram_id and str(owner_telegram_id) == user_id:
        return True

    redis = await get_redis()
    key = f"demo_msg_count:{user_id}"
    count = await redis.get(key)

    if count is not None and int(count) >= DEMO_MESSAGE_LIMIT:
        return False

    return True


async def _increment_demo_count(user_id: str, owner_telegram_id: Optional[int]) -> None:
    """Increment the demo message counter for non-owner users."""
    if owner_telegram_id and str(owner_telegram_id) == user_id:
        return  # Don't count owner messages

    redis = await get_redis()
    key = f"demo_msg_count:{user_id}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 86400 * 30)  # Expire after 30 days
    await pipe.execute()


async def handle_message(
    message: Message,
    bot: Bot,
    engine: ConversationEngine,
    shop_id: str,
    shop_config: Optional[dict] = None,
) -> None:
    """Handle incoming text message from Telegram.

    Args:
        message: Telegram message object
        bot: Bot instance for the shop
        engine: ConversationEngine instance
        shop_id: UUID of the shop
        shop_config: Shop configuration dict (includes owner_telegram_id)
    """
    if not message.text:
        await message.answer("Пока я понимаю только текстовые сообщения.")
        return

    user_id = str(message.from_user.id)
    username = message.from_user.username
    owner_telegram_id = (shop_config or {}).get("owner_telegram_id")

    logger.info(
        "message_received",
        shop_id=shop_id,
        user_id=user_id,
        text_preview=message.text[:50],
    )

    # Check daily new users limit (anti-abuse: max 100 new users/day)
    daily_ok = await _check_daily_new_users_limit(user_id, owner_telegram_id)
    if not daily_ok:
        await message.answer(DAILY_LIMIT_TEXT)
        return

    # Check demo message limit (skip for /start so users get the greeting)
    lower_text = message.text.lower().strip()
    if lower_text not in ("/start", "start", "начать"):
        allowed = await _check_demo_limit(user_id, owner_telegram_id)
        if not allowed:
            await message.answer(DEMO_LIMIT_TEXT)
            return

    try:
        result: StepResult = await engine.handle_message(
            shop_id=shop_id,
            user_id=user_id,
            message_text=message.text,
            user_telegram_username=username,
        )
    except Exception as e:
        import traceback
        logger.error(
            "handle_message_error",
            error=str(e),
            error_type=type(e).__name__,
            traceback=traceback.format_exc(),
            user_id=user_id,
            text_preview=message.text[:50] if message.text else "",
        )
        await message.answer(
            "Хм, что-то у меня не сложилось. Повторите, пожалуйста, "
            "или напишите «мастер» — подключу живого специалиста."
        )
        return

    # Register new user in daily counter (before incrementing msg count)
    await _increment_daily_new_users(user_id, owner_telegram_id)

    # Increment demo counter after successful processing
    await _increment_demo_count(user_id, owner_telegram_id)

    await _send_result(message, result)


async def handle_callback(
    callback: CallbackQuery,
    bot: Bot,
    engine: ConversationEngine,
    shop_id: str,
    shop_config: Optional[dict] = None,
) -> None:
    """Handle inline keyboard callback.

    Args:
        callback: Telegram callback query
        bot: Bot instance
        engine: ConversationEngine instance
        shop_id: UUID of the shop
        shop_config: Shop configuration dict (includes owner_telegram_id)
    """
    if not callback.data:
        await callback.answer()
        return

    user_id = str(callback.from_user.id)
    owner_telegram_id = (shop_config or {}).get("owner_telegram_id")

    # Check daily new users limit
    daily_ok = await _check_daily_new_users_limit(user_id, owner_telegram_id)
    if not daily_ok:
        await callback.answer()
        if callback.message:
            await callback.message.answer(DAILY_LIMIT_TEXT)
        return

    # Check demo limit for callbacks too
    allowed = await _check_demo_limit(user_id, owner_telegram_id)
    if not allowed:
        await callback.answer(DEMO_LIMIT_TEXT[:200])  # callback answer max 200 chars
        if callback.message:
            await callback.message.answer(DEMO_LIMIT_TEXT)
        return

    logger.info(
        "callback_received",
        shop_id=shop_id,
        user_id=user_id,
        data=callback.data,
    )

    try:
        result: StepResult = await engine.handle_callback(
            shop_id=shop_id,
            user_id=user_id,
            callback_data=callback.data,
        )
    except Exception as e:
        logger.error("handle_callback_error", error=str(e), user_id=user_id)
        await callback.answer("Ошибка")
        if callback.message:
            await callback.message.answer(
                "Хм, что-то не сработало. Попробуйте ещё раз "
                "или напишите «мастер»."
            )
        return

    # Increment demo counter after successful processing
    await _increment_demo_count(user_id, owner_telegram_id)

    # Answer the callback to remove loading state
    await callback.answer()

    # Send response
    if callback.message:
        await _send_result(callback.message, result)


async def _send_result(message: Message, result: StepResult) -> None:
    """Send StepResult as a Telegram message.

    If response_text is empty (e.g. conversation is in human mode),
    no message is sent — the master will respond directly.
    """
    if not result.response_text:
        # Empty response means bot is silenced (human mode active)
        logger.debug(
            "send_result_skipped_empty",
            user_id=str(message.from_user.id) if message.from_user else "unknown",
        )
        return

    if result.keyboard:
        await message.answer(
            text=result.response_text,
            reply_markup=result.keyboard,
        )
    else:
        await message.answer(text=result.response_text)
