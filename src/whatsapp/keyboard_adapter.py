"""Keyboard adapter — converts InlineKeyboardMarkup to numbered text for WhatsApp.

WhatsApp doesn't support inline buttons, so we:
1. Convert keyboard buttons → numbered text list
2. Store the mapping (number → callback_data) in Redis
3. When user replies with a number, resolve it back to callback_data
"""

from __future__ import annotations

import json
from typing import Optional

import redis.asyncio as aioredis
import structlog
from aiogram.types import InlineKeyboardMarkup

logger = structlog.get_logger()

# Redis key TTL — same as session TTL (2 hours)
MENU_TTL = 7200


def _menu_key(shop_id: str, user_id: str) -> str:
    """Redis key for the active menu mapping."""
    return f"wa_menu:{shop_id}:{user_id}"


def keyboard_to_text(keyboard: InlineKeyboardMarkup) -> tuple[str, dict[str, str]]:
    """Convert InlineKeyboardMarkup to numbered text list + mapping dict.

    Args:
        keyboard: aiogram InlineKeyboardMarkup

    Returns:
        (text_block, mapping) where:
          - text_block is like "1. 📱 Смартфон\\n2. 💻 Ноутбук\\n..."
          - mapping is {"1": "device:smartphone", "2": "device:laptop", ...}
    """
    lines: list[str] = []
    mapping: dict[str, str] = {}
    idx = 1

    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data:
                lines.append(f"{idx}. {button.text}")
                mapping[str(idx)] = button.callback_data
                # Also map the button text (lowercased, stripped of emoji)
                clean_text = button.text.strip()
                mapping[clean_text.lower()] = button.callback_data
                idx += 1

    return "\n".join(lines), mapping


async def save_menu(
    redis_client: aioredis.Redis,
    shop_id: str,
    user_id: str,
    mapping: dict[str, str],
) -> None:
    """Save current menu mapping to Redis."""
    key = _menu_key(shop_id, user_id)
    await redis_client.setex(key, MENU_TTL, json.dumps(mapping, ensure_ascii=False))
    logger.debug(
        "wa_menu_saved",
        shop_id=shop_id,
        user_id=user_id,
        options=len([k for k in mapping if k.isdigit()]),
    )


async def resolve_menu_choice(
    redis_client: aioredis.Redis,
    shop_id: str,
    user_id: str,
    user_text: str,
) -> Optional[str]:
    """Try to resolve user's text input against saved menu.

    Checks: exact digit match → exact text match (case-insensitive).

    Args:
        redis_client: Redis connection
        shop_id: Shop UUID string
        user_id: User phone number (WhatsApp)
        user_text: Raw user message text

    Returns:
        callback_data string if matched, None otherwise
    """
    key = _menu_key(shop_id, user_id)
    data = await redis_client.get(key)

    if not data:
        return None

    mapping: dict[str, str] = json.loads(data)
    text = user_text.strip()

    # Try exact match (number or text)
    if text in mapping:
        return mapping[text]

    # Try case-insensitive text match
    lower = text.lower()
    if lower in mapping:
        return mapping[lower]

    return None


async def clear_menu(
    redis_client: aioredis.Redis,
    shop_id: str,
    user_id: str,
) -> None:
    """Clear the menu mapping (e.g. after successful selection)."""
    key = _menu_key(shop_id, user_id)
    await redis_client.delete(key)
