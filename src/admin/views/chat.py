"""Master chat views — takeover, release, send messages, polling."""

from __future__ import annotations

import uuid
import pathlib
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.dependencies import get_current_shop
from src.database import get_db
from src.models.conversation import Conversation, Message
from src.models.shop import Shop

logger = structlog.get_logger()

router = APIRouter(prefix="/admin/chat", tags=["admin-chat"])

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Quick reply templates
QUICK_REPLIES: dict[str, str] = {
    "accept_today": "Можем принять сегодня. Подъезжайте!",
    "accept_tomorrow": "Можем принять завтра. Удобно?",
    "need_diagnostic": "Для точной оценки нужна диагностика. Стоимость — бесплатно.",
    "send_photo": "Пришлите, пожалуйста, фото устройства 📸",
    "will_call": "Наш мастер перезвонит вам в ближайшее время.",
}


async def send_telegram_message(shop: Shop, user_id: str, text: str) -> bool:
    """Send a message to a Telegram user via the shop's bot."""
    from src.bot.factory import get_or_create_bot
    if not shop.telegram_bot_token:
        logger.warning("send_telegram_no_token", shop_id=str(shop.id))
        return False
    try:
        bot = await get_or_create_bot(shop.telegram_bot_token)
        await bot.send_message(chat_id=int(user_id), text=text)
        return True
    except Exception as e:
        logger.error(
            "send_telegram_error",
            error=str(e),
            user_id=user_id,
            shop_id=str(shop.id),
        )
        return False


async def send_whatsapp_message(shop: Shop, user_phone: str, text: str) -> bool:
    """Send a message to a WhatsApp user via Twilio."""
    from src.whatsapp.client import get_whatsapp_client

    wa_client = get_whatsapp_client()
    if not wa_client:
        logger.warning("send_whatsapp_no_client", shop_id=str(shop.id))
        return False
    try:
        await wa_client.send_message(user_phone, text)
        return True
    except Exception as e:
        logger.error(
            "send_whatsapp_error",
            error=str(e),
            user_phone=user_phone,
            shop_id=str(shop.id),
        )
        return False


async def send_to_channel(
    shop: Shop, conversation: Conversation, text: str
) -> bool:
    """Send a message to the customer via the appropriate channel."""
    if conversation.channel == "whatsapp":
        return await send_whatsapp_message(
            shop, conversation.external_user_id, text
        )
    return await send_telegram_message(
        shop, conversation.external_user_id, text
    )


async def _get_conversation_for_shop(
    conversation_id: str,
    shop: Shop,
    db: AsyncSession,
) -> Optional[Conversation]:
    """Fetch conversation and verify it belongs to the current shop."""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        return None

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.shop_id == shop.id,
        )
    )
    return result.scalar_one_or_none()


async def _save_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    step_name: str = "human_chat",
) -> Message:
    """Save a message to the database and return it."""
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        step_name=step_name,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


async def _render_chat_panel(
    request: Request,
    conversation: Conversation,
    messages: list,
    shop: Shop,
    flash: Optional[str] = None,
) -> HTMLResponse:
    """Render the chat panel partial template."""
    return templates.TemplateResponse(
        "chat/panel.html",
        {
            "request": request,
            "conversation": conversation,
            "messages": messages,
            "shop": shop,
            "flash": flash,
        },
    )


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.post("/{conversation_id}/takeover", response_class=HTMLResponse)
async def takeover(
    request: Request,
    conversation_id: str,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Set conversation mode to human, notify customer, return updated chat panel."""
    if shop is None:
        return HTMLResponse("Unauthorized", status_code=401)

    conversation = await _get_conversation_for_shop(conversation_id, shop, db)
    if not conversation:
        return HTMLResponse("Диалог не найден", status_code=404)

    now = datetime.now(timezone.utc)

    # Update conversation mode and status
    await db.execute(
        sa_update(Conversation)
        .where(Conversation.id == conversation.id)
        .values(
            mode="human",
            status="human_active",
            last_message_at=now,
        )
    )

    # Save notification message as bot role
    notice_text = "Сейчас с вами свяжется наш специалист 👨‍🔧"
    await _save_message(db, conversation.id, "bot", notice_text, step_name="takeover")

    await db.commit()

    # Send to customer (Telegram or WhatsApp)
    await send_to_channel(shop, conversation, notice_text)

    logger.info(
        "chat_takeover",
        conversation_id=conversation_id,
        shop_id=str(shop.id),
    )

    # Reload fresh conversation + messages
    await db.refresh(conversation)
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return await _render_chat_panel(request, conversation, messages, shop)


@router.post("/{conversation_id}/release", response_class=HTMLResponse)
async def release(
    request: Request,
    conversation_id: str,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Return conversation to bot mode."""
    if shop is None:
        return HTMLResponse("Unauthorized", status_code=401)

    conversation = await _get_conversation_for_shop(conversation_id, shop, db)
    if not conversation:
        return HTMLResponse("Диалог не найден", status_code=404)

    now = datetime.now(timezone.utc)

    await db.execute(
        sa_update(Conversation)
        .where(Conversation.id == conversation.id)
        .values(
            mode="bot",
            status="active",
            last_message_at=now,
        )
    )

    release_text = "Спасибо за ожидание! Бот снова на связи 🤖"
    await _save_message(db, conversation.id, "bot", release_text, step_name="release")

    await db.commit()

    await send_to_channel(shop, conversation, release_text)

    logger.info(
        "chat_released",
        conversation_id=conversation_id,
        shop_id=str(shop.id),
    )

    await db.refresh(conversation)
    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return await _render_chat_panel(request, conversation, messages, shop)


@router.post("/{conversation_id}/send", response_class=HTMLResponse)
async def send_message(
    request: Request,
    conversation_id: str,
    text: str = Form(...),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Send a message from the master to the customer."""
    if shop is None:
        return HTMLResponse("Unauthorized", status_code=401)

    if not text.strip():
        return HTMLResponse("Пустое сообщение", status_code=400)

    conversation = await _get_conversation_for_shop(conversation_id, shop, db)
    if not conversation:
        return HTMLResponse("Диалог не найден", status_code=404)

    now = datetime.now(timezone.utc)

    # Save master message
    msg = await _save_message(
        db, conversation.id, "master", text.strip(), step_name="human_chat"
    )

    # Update last_message_at on the conversation
    await db.execute(
        sa_update(Conversation)
        .where(Conversation.id == conversation.id)
        .values(last_message_at=now)
    )

    await db.commit()

    # Send to customer (Telegram or WhatsApp)
    await send_to_channel(shop, conversation, text.strip())

    logger.info(
        "master_message_sent",
        conversation_id=conversation_id,
        shop_id=str(shop.id),
        text_len=len(text),
    )

    # Return the single new message bubble (appended to existing list)
    return templates.TemplateResponse(
        "chat/message_bubble.html",
        {
            "request": request,
            "msg": msg,
        },
    )


@router.get("/{conversation_id}/messages", response_class=HTMLResponse)
async def poll_messages(
    request: Request,
    conversation_id: str,
    after: Optional[str] = Query(None),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Poll for new messages since a given ISO timestamp (for HTMX polling)."""
    if shop is None:
        return HTMLResponse("", status_code=200)

    conversation = await _get_conversation_for_shop(conversation_id, shop, db)
    if not conversation:
        return HTMLResponse("", status_code=200)

    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        return HTMLResponse("", status_code=200)

    stmt = (
        select(Message)
        .where(Message.conversation_id == conv_uuid)
        .order_by(Message.created_at.asc())
    )

    if after:
        try:
            # Parse ISO timestamp — handle both with and without timezone info
            after_dt = datetime.fromisoformat(after.replace("Z", "+00:00"))
            stmt = stmt.where(Message.created_at > after_dt)
        except ValueError:
            pass  # Ignore malformed timestamp — return all messages

    result = await db.execute(stmt)
    new_messages = result.scalars().all()

    if not new_messages:
        return HTMLResponse("", status_code=200)

    # Return multiple message bubbles
    return templates.TemplateResponse(
        "chat/messages_partial.html",
        {
            "request": request,
            "messages": new_messages,
        },
    )


@router.post("/{conversation_id}/quick-reply", response_class=HTMLResponse)
async def quick_reply(
    request: Request,
    conversation_id: str,
    template: str = Form(...),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Send a predefined quick-reply template as master message."""
    if shop is None:
        return HTMLResponse("Unauthorized", status_code=401)

    text = QUICK_REPLIES.get(template)
    if not text:
        return HTMLResponse("Неизвестный шаблон", status_code=400)

    conversation = await _get_conversation_for_shop(conversation_id, shop, db)
    if not conversation:
        return HTMLResponse("Диалог не найден", status_code=404)

    now = datetime.now(timezone.utc)

    msg = await _save_message(
        db, conversation.id, "master", text, step_name="human_chat"
    )

    await db.execute(
        sa_update(Conversation)
        .where(Conversation.id == conversation.id)
        .values(last_message_at=now)
    )

    await db.commit()

    await send_to_channel(shop, conversation, text)

    logger.info(
        "quick_reply_sent",
        conversation_id=conversation_id,
        template=template,
        shop_id=str(shop.id),
    )

    # Return the new message bubble appended to the chat
    return templates.TemplateResponse(
        "chat/message_bubble.html",
        {
            "request": request,
            "msg": msg,
        },
    )
