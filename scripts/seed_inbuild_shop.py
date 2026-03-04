"""Create InBuild shop record in DB with @BuildMate_bot token.

Run once: python -m scripts.seed_inbuild_shop

Also adds the product_type column to shops table if it doesn't exist.
"""

import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.config import settings
from src.models.base import Base
from src.models.shop import Shop


async def seed_inbuild_shop():
    """Create or update the InBuild demo shop."""
    engine = create_async_engine(settings.database_url)

    # Add product_type column if it doesn't exist (no Alembic in this project)
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE shops ADD COLUMN IF NOT EXISTS "
            "product_type VARCHAR(30) DEFAULT 'auto_repair'"
        ))
        print("Ensured product_type column exists")

    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with session_factory() as session:
        # Check if shop already exists
        result = await session.execute(
            select(Shop).where(Shop.slug == "buildmate-demo")
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Shop 'buildmate-demo' already exists (id={existing.id})")
            print(f"  product_type: {existing.product_type}")
            print(f"  bot token set: {bool(existing.telegram_bot_token)}")
            # Update token if needed
            if existing.telegram_bot_token != settings.inbuild_bot_token:
                existing.telegram_bot_token = settings.inbuild_bot_token
                existing.product_type = "inbuild"
                await session.commit()
                print("  -> Updated bot token and product_type")
            return

        shop = Shop(
            slug="buildmate-demo",
            name="BuildMate Demo",
            product_type="inbuild",
            telegram_bot_token=settings.inbuild_bot_token,
            telegram_bot_username="BuildMate_bot",
            owner_telegram_id=75524586,  # Anastasia's chat_id
            greeting_text=None,  # Use default from engine
            language="ru",
            timezone="Asia/Tbilisi",
            currency="USD",
            bot_personality="friendly",
            collect_phone=True,
            collect_name=True,
            offer_appointment=False,
            plan="free",
            plan_conversations_limit=200,
            address="Тбилиси, Грузия",
            is_active=True,
        )
        session.add(shop)
        await session.flush()
        shop_id = shop.id
        await session.commit()
        print(f"Created InBuild shop (id={shop_id})")
        print(f"  slug: buildmate-demo")
        print(f"  product_type: inbuild")
        print(f"  bot: @BuildMate_bot")
        print(f"  timezone: Asia/Tbilisi")
        print(f"  currency: USD")

    await engine.dispose()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(seed_inbuild_shop())
