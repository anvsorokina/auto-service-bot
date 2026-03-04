"""Session manager — Redis CRUD for conversation state.

Supports multiple session state models (auto-repair SessionState,
construction BuildSessionState, etc.) via the `state_model` parameter.
"""

from typing import Optional, Type, TypeVar, Union

import redis.asyncio as redis
import structlog

from src.config import settings
from src.schemas.conversation import SessionState

logger = structlog.get_logger()

# Generic type for any Pydantic model with .model_validate_json / .model_dump_json
T = TypeVar("T")


class SessionManager:
    """Manages conversation state in Redis with TTL.

    By default works with auto-repair SessionState.
    Pass a different state_model to support other products.
    """

    def __init__(self, redis_client: redis.Redis, state_model: Type[T] = SessionState):
        self.redis = redis_client
        self.ttl = settings.session_ttl_seconds
        self.state_model = state_model

    def _key(self, shop_id: str, user_id: str) -> str:
        return f"session:{shop_id}:{user_id}"

    async def get(self, shop_id: str, user_id: str) -> Optional[T]:
        """Get session state from Redis."""
        data = await self.redis.get(self._key(shop_id, user_id))
        if data:
            return self.state_model.model_validate_json(data)
        return None

    async def save(self, shop_id: str, user_id: str, state: T) -> None:
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
            step=state.current_step.value if hasattr(state, 'current_step') else "unknown",
        )

    async def delete(self, shop_id: str, user_id: str) -> None:
        """Delete session from Redis."""
        await self.redis.delete(self._key(shop_id, user_id))

    async def exists(self, shop_id: str, user_id: str) -> bool:
        """Check if session exists."""
        return bool(await self.redis.exists(self._key(shop_id, user_id)))
