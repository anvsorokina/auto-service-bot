"""Main message handler — routes all incoming messages through ConversationEngine."""

import structlog
from aiogram import Bot
from aiogram.types import Message, CallbackQuery

from src.conversation.engine import ConversationEngine
from src.conversation.steps.base import StepResult

logger = structlog.get_logger()


async def handle_message(
    message: Message,
    bot: Bot,
    engine: ConversationEngine,
    shop_id: str,
) -> None:
    """Handle incoming text message from Telegram.

    Args:
        message: Telegram message object
        bot: Bot instance for the shop
        engine: ConversationEngine instance
        shop_id: UUID of the shop
    """
    if not message.text:
        await message.answer("Пока я понимаю только текстовые сообщения.")
        return

    user_id = str(message.from_user.id)
    username = message.from_user.username

    logger.info(
        "message_received",
        shop_id=shop_id,
        user_id=user_id,
        text_preview=message.text[:50],
    )

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

    await _send_result(message, result)


async def handle_callback(
    callback: CallbackQuery,
    bot: Bot,
    engine: ConversationEngine,
    shop_id: str,
) -> None:
    """Handle inline keyboard callback.

    Args:
        callback: Telegram callback query
        bot: Bot instance
        engine: ConversationEngine instance
        shop_id: UUID of the shop
    """
    if not callback.data:
        await callback.answer()
        return

    user_id = str(callback.from_user.id)

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
