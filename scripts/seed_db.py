"""Seed database with initial reference data (device categories, repair types)."""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.config import settings
from src.models.base import Base
from src.models.device import DeviceCategory, RepairType


DEVICE_CATEGORIES = [
    {"slug": "smartphone", "name_ru": "Смартфон", "name_en": "Smartphone", "icon": "📱"},
    {"slug": "laptop", "name_ru": "Ноутбук", "name_en": "Laptop", "icon": "💻"},
    {"slug": "tablet", "name_ru": "Планшет", "name_en": "Tablet", "icon": "📟"},
    {"slug": "smartwatch", "name_ru": "Умные часы", "name_en": "Smartwatch", "icon": "⌚"},
    {"slug": "headphones", "name_ru": "Наушники", "name_en": "Headphones", "icon": "🎧"},
    {"slug": "game_console", "name_ru": "Игровая консоль", "name_en": "Game Console", "icon": "🎮"},
]

REPAIR_TYPES = [
    {"slug": "screen_replacement", "name_ru": "Замена экрана", "name_en": "Screen Replacement", "category": "smartphone", "duration": 60},
    {"slug": "battery_replacement", "name_ru": "Замена аккумулятора", "name_en": "Battery Replacement", "category": "smartphone", "duration": 30},
    {"slug": "water_damage", "name_ru": "Ремонт после воды", "name_en": "Water Damage Repair", "category": "smartphone", "duration": 120},
    {"slug": "charging_port", "name_ru": "Ремонт разъёма зарядки", "name_en": "Charging Port Repair", "category": "smartphone", "duration": 45},
    {"slug": "camera_repair", "name_ru": "Ремонт камеры", "name_en": "Camera Repair", "category": "smartphone", "duration": 45},
    {"slug": "speaker_repair", "name_ru": "Ремонт динамика", "name_en": "Speaker Repair", "category": "smartphone", "duration": 30},
    {"slug": "back_glass", "name_ru": "Замена задней крышки", "name_en": "Back Glass Replacement", "category": "smartphone", "duration": 60},
    {"slug": "button_repair", "name_ru": "Ремонт кнопок", "name_en": "Button Repair", "category": "smartphone", "duration": 30},
    {"slug": "software_issue", "name_ru": "Программная проблема", "name_en": "Software Issue", "category": "smartphone", "duration": 30},
]


async def seed():
    """Seed the database with reference data."""
    engine = create_async_engine(settings.database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with session_factory() as session:
        # Seed device categories
        category_map = {}
        for cat_data in DEVICE_CATEGORIES:
            cat = DeviceCategory(**cat_data)
            session.add(cat)
            await session.flush()
            category_map[cat_data["slug"]] = cat.id
            print(f"  + Category: {cat_data['name_ru']}")

        # Seed repair types
        for rt_data in REPAIR_TYPES:
            cat_slug = rt_data.pop("category")
            duration = rt_data.pop("duration")
            rt = RepairType(
                **rt_data,
                device_category_id=category_map.get(cat_slug),
                typical_duration_minutes=duration,
            )
            session.add(rt)
            print(f"  + Repair: {rt_data['name_ru']}")

        await session.commit()

    await engine.dispose()
    print("\nSeed completed!")


if __name__ == "__main__":
    asyncio.run(seed())
