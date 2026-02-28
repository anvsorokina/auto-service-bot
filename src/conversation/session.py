"""Session manager — Redis CRUD for conversation state."""

from typing import Optional

import redis.asyncio as redis
import structlog

from src.config import settings
from src.schemas.conversation import SessionState

logger = structlog.get_logger()


class SessionManager:
    """Manages conversation state in Redis with TTL."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.ttl = settings.session_ttl_seconds

    def _key(self, shop_id: str, user_id: str) -> str:
        return f"session:{shop_id}:{user_id}"

    async def get(self, shop_id: str, user_id: str) -> Optional[SessionState]:
        """Get session state from Redis."""
        data = await self.redis.get(self._key(shop_id, user_id))
        if data:
            return SessionState.model_validate_json(data)
        return None

    async def save(self, shop_id: str, user_id: str, state: SessionState) -> None:
        """Save session state to Redis with TTL."""
        await self.redis.setex(
            self._key(shop_id, user_id),
            self.ttl,
            state.model_dump_json(),
        )
        logger.debug(
            "session_saved",
            shop_id=shop_id,
            user_id=user_id,
            step=state.current_step.value,
        )

    async def delete(self, shop_id: str, user_id: str) -> None:
        """Delete session from Redis."""
        await self.redis.delete(self._key(shop_id, user_id))

    async def exists(self, shop_id: str, user_id: str) -> bool:
        """Check if session exists."""
        return bool(await self.redis.exists(self._key(shop_id, user_id)))
