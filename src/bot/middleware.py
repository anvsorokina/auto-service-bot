"""Shop middleware — resolves shop from webhook token."""

from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.shop import Shop

logger = structlog.get_logger()


async def get_shop_by_token(
    db: AsyncSession, bot_token: str
) -> Optional[Shop]:
    """Find shop by its Telegram bot token.

    Args:
        db: Database session
        bot_token: Telegram bot token from the webhook URL

    Returns:
        Shop object or None
    """
    stmt = select(Shop).where(
        Shop.telegram_bot_token == bot_token,
        Shop.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()

    if shop:
        logger.debug("shop_resolved", shop_id=str(shop.id), slug=shop.slug)
    else:
        logger.warning("shop_not_found", token_prefix=bot_token[:10])

    return shop


async def get_shop_by_slug(
    db: AsyncSession, slug: str
) -> Optional[Shop]:
    """Find shop by slug.

    Args:
        db: Database session
        slug: Shop slug

    Returns:
        Shop object or None
    """
    stmt = select(Shop).where(Shop.slug == slug, Shop.is_active == True)  # noqa: E712
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
