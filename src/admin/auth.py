"""Telegram Login authentication + Redis session management."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Optional

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger()

SESSION_TTL = 86400  # 24 hours
SESSION_PREFIX = "admin_session:"


def verify_telegram_login(data: dict, bot_token: str) -> bool:
    """Verify Telegram Login Widget data using bot token.

    Telegram sends: id, first_name, last_name, username, photo_url, auth_date, hash.
    We verify the hash using HMAC-SHA256 with SHA256(bot_token) as key.

    Args:
        data: Dict from Telegram Login Widget callback
        bot_token: The Telegram bot token for this shop

    Returns:
        True if the hash is valid
    """
    check_hash = data.get("hash", "")
    if not check_hash:
        return False

    # Build data-check-string: all fields except hash, sorted alphabetically
    filtered = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(filtered.items())
    )

    # Secret key = SHA256(bot_token)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()

    # HMAC-SHA256
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_hash, check_hash)


async def create_session(
    redis: Redis,
    shop_id: str,
    telegram_id: int,
    shop_name: str = "",
) -> str:
    """Create admin session in Redis.

    Args:
        redis: Redis client
        shop_id: UUID of the shop
        telegram_id: Owner's Telegram user ID
        shop_name: Shop name for display

    Returns:
        Session token (random string)
    """
    token = secrets.token_urlsafe(32)
    session_data = json.dumps({
        "shop_id": shop_id,
        "telegram_id": telegram_id,
        "shop_name": shop_name,
    })

    await redis.setex(
        f"{SESSION_PREFIX}{token}",
        SESSION_TTL,
        session_data,
    )

    logger.info(
        "admin_session_created",
        shop_id=shop_id,
        telegram_id=telegram_id,
    )

    return token


async def get_session(redis: Redis, token: str) -> Optional[dict]:
    """Get session data from Redis.

    Args:
        redis: Redis client
        token: Session token from cookie

    Returns:
        Session dict with shop_id, telegram_id, shop_name or None
    """
    if not token:
        return None

    data = await redis.get(f"{SESSION_PREFIX}{token}")
    if not data:
        return None

    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None


async def delete_session(redis: Redis, token: str) -> None:
    """Delete admin session from Redis."""
    await redis.delete(f"{SESSION_PREFIX}{token}")
