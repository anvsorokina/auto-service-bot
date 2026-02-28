"""Test fixtures and configuration."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from src.conversation.engine import ConversationEngine
from src.conversation.session import SessionManager
from src.schemas.conversation import CollectedData, ConversationStep, SessionState


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    return redis


@pytest.fixture
def session_manager(mock_redis):
    """Create SessionManager with mock Redis."""
    return SessionManager(mock_redis)


@pytest.fixture
def engine(session_manager):
    """Create ConversationEngine."""
    return ConversationEngine(session_manager)


@pytest.fixture
def sample_session():
    """Create a sample session state."""
    return SessionState(
        conversation_id=str(uuid.uuid4()),
        shop_id=str(uuid.uuid4()),
        current_step=ConversationStep.GREETING,
        collected=CollectedData(),
    )


@pytest.fixture
def sample_session_with_device():
    """Create a session with device info already collected."""
    return SessionState(
        conversation_id=str(uuid.uuid4()),
        shop_id=str(uuid.uuid4()),
        current_step=ConversationStep.PROBLEM,
        collected=CollectedData(
            device_category="smartphone",
            device_brand="Apple",
            device_model="iPhone 15 Pro",
        ),
    )
