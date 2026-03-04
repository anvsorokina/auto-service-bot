"""Tests for InBuild construction conversation engine."""

import pytest
import uuid
from unittest.mock import AsyncMock, patch

from src.conversation.session import SessionManager
from src.products.inbuild.engine import BuildConversationEngine
from src.products.inbuild.schemas import BuildStep, BuildCollectedData, BuildSessionState


@pytest.fixture
def build_mock_redis():
    """Mock Redis client for build tests."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    redis.exists = AsyncMock(return_value=False)
    return redis


@pytest.fixture
def build_session_manager(build_mock_redis):
    """Create SessionManager with mock Redis for build sessions."""
    return SessionManager(build_mock_redis, state_model=BuildSessionState)


@pytest.fixture
def build_engine(build_session_manager):
    """Create BuildConversationEngine."""
    return BuildConversationEngine(build_session_manager)


@pytest.fixture
def sample_build_session():
    """Create a sample build session state."""
    return BuildSessionState(
        conversation_id=str(uuid.uuid4()),
        shop_id=str(uuid.uuid4()),
        current_step=BuildStep.GREETING,
        collected=BuildCollectedData(),
    )


class TestBuildConversationEngine:
    """Test build engine message handling."""

    @pytest.mark.asyncio
    async def test_start_creates_new_session(self, build_engine):
        result = await build_engine.handle_message(
            shop_id="shop-1",
            user_id="user-1",
            message_text="/start",
        )
        assert result.response_text
        # Greeting should mention construction/repair/build-related content

    @pytest.mark.asyncio
    async def test_master_command_handoff(self, build_engine):
        result = await build_engine.handle_message(
            shop_id="shop-1",
            user_id="user-1",
            message_text="мастер",
        )
        assert "специалист" in result.response_text.lower() or "свяжу" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_callback_service_selection(self, build_engine, build_mock_redis):
        # First start a session
        await build_engine.handle_message(
            shop_id="shop-1",
            user_id="user-1",
            message_text="/start",
        )

        # Mock existing session
        state = BuildSessionState(
            conversation_id="conv-1",
            shop_id="shop-1",
            current_step=BuildStep.GREETING,
            collected=BuildCollectedData(),
        )
        build_mock_redis.get = AsyncMock(return_value=state.model_dump_json())

        result = await build_engine.handle_callback(
            shop_id="shop-1",
            user_id="user-1",
            callback_data="service:renovation",
        )
        assert result.response_text

    @pytest.mark.asyncio
    async def test_callback_property_selection(self, build_engine, build_mock_redis):
        state = BuildSessionState(
            conversation_id="conv-1",
            shop_id="shop-1",
            current_step=BuildStep.PROPERTY_INFO,
            collected=BuildCollectedData(service_category="renovation"),
        )
        build_mock_redis.get = AsyncMock(return_value=state.model_dump_json())

        result = await build_engine.handle_callback(
            shop_id="shop-1",
            user_id="user-1",
            callback_data="property:apartment",
        )
        assert result.response_text

    @pytest.mark.asyncio
    async def test_callback_scope_selection(self, build_engine, build_mock_redis):
        state = BuildSessionState(
            conversation_id="conv-1",
            shop_id="shop-1",
            current_step=BuildStep.PROJECT_DESCRIPTION,
            collected=BuildCollectedData(
                service_category="renovation",
                property_type="apartment",
            ),
        )
        build_mock_redis.get = AsyncMock(return_value=state.model_dump_json())

        result = await build_engine.handle_callback(
            shop_id="shop-1",
            user_id="user-1",
            callback_data="scope:cosmetic",
        )
        assert result.response_text

    @pytest.mark.asyncio
    async def test_callback_no_session_expired(self, build_engine):
        result = await build_engine.handle_callback(
            shop_id="shop-1",
            user_id="user-1",
            callback_data="service:renovation",
        )
        assert "истекла" in result.response_text.lower() or "start" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_unknown_callback_prefix(self, build_engine, build_mock_redis):
        state = BuildSessionState(
            conversation_id="conv-1",
            shop_id="shop-1",
            current_step=BuildStep.GREETING,
            collected=BuildCollectedData(),
        )
        build_mock_redis.get = AsyncMock(return_value=state.model_dump_json())

        result = await build_engine.handle_callback(
            shop_id="shop-1",
            user_id="user-1",
            callback_data="unknown:something",
        )
        assert "попробуйте" in result.response_text.lower() or "понял" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_service_other_goes_to_free_text(self, build_engine, build_mock_redis):
        state = BuildSessionState(
            conversation_id="conv-1",
            shop_id="shop-1",
            current_step=BuildStep.GREETING,
            collected=BuildCollectedData(),
        )
        build_mock_redis.get = AsyncMock(return_value=state.model_dump_json())

        result = await build_engine.handle_callback(
            shop_id="shop-1",
            user_id="user-1",
            callback_data="service:other",
        )
        assert result.response_text
        # Should ask the user to describe what work they need


class TestBuildSessionState:
    """Test BuildSessionState serialization."""

    def test_serialize_deserialize(self):
        state = BuildSessionState(
            conversation_id=str(uuid.uuid4()),
            shop_id=str(uuid.uuid4()),
            current_step=BuildStep.SERVICE_TYPE,
            collected=BuildCollectedData(
                service_category="renovation",
                property_type="apartment",
                property_area_sqm=85.0,
                budget_currency="USD",
            ),
            messages_count=3,
        )
        json_str = state.model_dump_json()
        restored = BuildSessionState.model_validate_json(json_str)
        assert restored.current_step == BuildStep.SERVICE_TYPE
        assert restored.collected.service_category == "renovation"
        assert restored.collected.property_area_sqm == 85.0
        assert restored.collected.budget_currency == "USD"
        assert restored.messages_count == 3

    def test_default_values(self):
        state = BuildSessionState(
            conversation_id="test",
            shop_id="test",
        )
        assert state.current_step == BuildStep.GREETING
        assert state.collected.budget_currency == "USD"
        assert state.messages_count == 0
        assert state.language == "ru"
        assert state.channel == "telegram"


class TestBuildMasterRequest:
    """Test handoff detection for construction."""

    def test_exact_master(self):
        assert BuildConversationEngine._is_master_request("мастер")

    def test_exact_specialist(self):
        assert BuildConversationEngine._is_master_request("специалист")

    def test_call_master(self):
        assert BuildConversationEngine._is_master_request("позовите мастера")

    def test_want_specialist(self):
        assert BuildConversationEngine._is_master_request("хочу поговорить со специалистом")

    def test_not_handoff_long_sentence(self):
        # "мастер" mentioned in context, not as a command
        assert not BuildConversationEngine._is_master_request(
            "мастер на все руки делает ремонт квартир и офисов уже десять лет"
        )
