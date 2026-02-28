"""Bot factory — creates and caches Bot instances per shop."""

from __future__ import annotations

from aiogram import Bot
from cachetools import TTLCache
import structlog

logger = structlog.get_logger()

# Cache bot instances for 5 minutes to avoid re-creating on each request
_bot_cache: TTLCache[str, Bot] = TTLCache(maxsize=100, ttl=300)


async def get_or_create_bot(telegram_token: str) -> Bot:
    """Get or create a cached Bot instance for a shop.

    Args:
        telegram_token: The shop's Telegram bot token

    Returns:
        Bot instance ready to use
    """
    if telegram_token not in _bot_cache:
        bot = Bot(token=telegram_token)
        _bot_cache[telegram_token] = bot
        logger.debug("bot_created", token_prefix=telegram_token[:10])
    return _bot_cache[telegram_token]


def clear_bot_cache() -> None:
    """Clear all cached bot instances."""
    _bot_cache.clear()
