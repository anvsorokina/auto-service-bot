"""FastAPI dependencies for admin panel authentication."""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import Cookie, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.admin.auth import get_session
from src.database import get_db
from src.models.shop import Shop
from src.redis_client import get_redis

logger = structlog.get_logger()


async def get_current_shop(
    request: Request,
    admin_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[Shop]:
    """Get the currently authenticated shop from session cookie.

    Returns None if not authenticated (views should redirect to login).
    """
    if not admin_token:
        return None

    redis = await get_redis()
    session = await get_session(redis, admin_token)
    if not session:
        return None

    shop_id = session.get("shop_id")
    if not shop_id:
        return None

    result = await db.execute(
        select(Shop).where(Shop.id == shop_id, Shop.is_active == True)  # noqa: E712
    )
    shop = result.scalar_one_or_none()

    return shop


async def require_auth(
    request: Request,
    shop: Optional[Shop] = Depends(get_current_shop),
):
    """Dependency that redirects to login if not authenticated.

    Use in routes that require authentication.
    Returns RedirectResponse or the shop.
    """
    if shop is None:
        return None
    return shop
