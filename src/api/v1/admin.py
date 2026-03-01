"""Admin API — shop management (superadmin)."""

import structlog
from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.factory import get_or_create_bot
from src.config import settings
from src.database import get_db
from src.models.shop import Shop
from src.schemas.shop import ShopCreate, ShopResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Validate the admin API key from X-Admin-Key header."""
    if not api_key or api_key != settings.admin_secret_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


@router.post("/shops", response_model=ShopResponse)
async def create_shop(
    data: ShopCreate,
    _key: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> ShopResponse:
    """Create a new shop and register its Telegram webhook.

    Args:
        data: Shop creation data
        db: Database session

    Returns:
        Created shop details
    """
    shop = Shop(
        slug=data.slug,
        name=data.name,
        telegram_bot_token=data.telegram_bot_token,
        owner_telegram_id=data.owner_telegram_id,
        language=data.language,
        currency=data.currency,
        timezone=data.timezone,
        greeting_text=data.greeting_text,
        address=data.address,
        maps_url=data.maps_url,
    )

    db.add(shop)
    await db.flush()

    # Register Telegram webhook
    try:
        bot = await get_or_create_bot(data.telegram_bot_token)
        webhook_url = (
            f"{settings.telegram_webhook_base_url}"
            f"/webhook/telegram/{data.telegram_bot_token}"
        )
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.telegram_webhook_secret,
        )
        # Get bot info
        bot_info = await bot.get_me()
        shop.telegram_bot_username = bot_info.username

        logger.info(
            "shop_created",
            slug=data.slug,
            webhook_url=webhook_url,
            bot_username=bot_info.username,
        )
    except Exception as e:
        logger.error("webhook_registration_failed", error=str(e), slug=data.slug)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register Telegram webhook: {e}",
        )

    await db.commit()

    return ShopResponse(
        id=str(shop.id),
        slug=shop.slug,
        name=shop.name,
        telegram_bot_username=shop.telegram_bot_username,
        language=shop.language,
        currency=shop.currency,
        is_active=shop.is_active,
    )


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
