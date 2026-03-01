"""Seed database with initial reference data (device categories, repair types)."""

import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.config import settings
from src.models.base import Base
from src.models.device import DeviceCategory, RepairType


DEVICE_CATEGORIES = [
    {"slug": "sedan", "name_ru": "Легковой", "name_en": "Sedan", "icon": "🚗"},
    {"slug": "suv", "name_ru": "Внедорожник / Кроссовер", "name_en": "SUV / Crossover", "icon": "🚙"},
    {"slug": "truck", "name_ru": "Грузовой", "name_en": "Truck", "icon": "🚛"},
    {"slug": "minivan", "name_ru": "Минивэн", "name_en": "Minivan", "icon": "🚐"},
    {"slug": "commercial", "name_ru": "Коммерческий транспорт", "name_en": "Commercial", "icon": "🚚"},
]

REPAIR_TYPES = [
    {"slug": "engine_repair", "name_ru": "Ремонт двигателя", "name_en": "Engine Repair", "category": "sedan", "duration": 240},
    {"slug": "brake_repair", "name_ru": "Ремонт тормозов", "name_en": "Brake Repair", "category": "sedan", "duration": 120},
    {"slug": "oil_change", "name_ru": "Замена масла / ТО", "name_en": "Oil Change / Maintenance", "category": "sedan", "duration": 60},
    {"slug": "suspension_repair", "name_ru": "Ремонт подвески", "name_en": "Suspension Repair", "category": "sedan", "duration": 180},
    {"slug": "diagnostics", "name_ru": "Диагностика", "name_en": "Diagnostics", "category": "sedan", "duration": 60},
    {"slug": "electrical", "name_ru": "Электрика", "name_en": "Electrical", "category": "sedan", "duration": 120},
    {"slug": "bodywork", "name_ru": "Кузов / покраска", "name_en": "Bodywork / Paint", "category": "sedan", "duration": 480},
    {"slug": "ac_repair", "name_ru": "Ремонт кондиционера", "name_en": "AC Repair", "category": "sedan", "duration": 120},
    {"slug": "transmission", "name_ru": "Ремонт коробки передач", "name_en": "Transmission Repair", "category": "sedan", "duration": 360},
    {"slug": "tire_service", "name_ru": "Шины / колёса", "name_en": "Tire Service", "category": "sedan", "duration": 60},
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
