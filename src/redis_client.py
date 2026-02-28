"""Redis async client for session storage."""

from typing import Optional

import redis.asyncio as redis

from src.config import settings

_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Get or create Redis client (lazy init)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _redis_client


async def get_redis() -> redis.Redis:
    """FastAPI dependency for Redis client."""
    return get_redis_client()
