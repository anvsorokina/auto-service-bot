"""Tests for conversation state machine and session management."""

import json
import uuid

import pytest

from src.schemas.conversation import CollectedData, ConversationStep, SessionState


class TestSessionState:
    """Test SessionState model."""

    def test_create_default(self):
        state = SessionState(
            conversation_id=str(uuid.uuid4()),
            shop_id=str(uuid.uuid4()),
        )
        assert state.current_step == ConversationStep.GREETING
        assert state.retry_count == 0
        assert state.language == "ru"
        assert state.collected.device_brand is None

    def test_serialize_deserialize(self):
        state = SessionState(
            conversation_id="test-conv-id",
            shop_id="test-shop-id",
            current_step=ConversationStep.DEVICE_MODEL,
            collected=CollectedData(
                device_category="smartphone",
                device_brand="Apple",
                device_model="iPhone 15 Pro",
            ),
        )
        json_str = state.model_dump_json()
        restored = SessionState.model_validate_json(json_str)

        assert restored.conversation_id == "test-conv-id"
        assert restored.current_step == ConversationStep.DEVICE_MODEL
        assert restored.collected.device_brand == "Apple"
        assert restored.collected.device_model == "iPhone 15 Pro"

    def test_step_ordering(self):
        steps = list(ConversationStep)
        assert steps[0] == ConversationStep.GREETING
        assert steps[-1] == ConversationStep.COMPLETED
        assert len(steps) == 10


class TestCollectedData:
    """Test CollectedData model."""

    def test_empty_data(self):
        data = CollectedData()
        assert data.device_brand is None
        assert data.customer_name is None
        assert data.estimated_price_min is None

    def test_partial_data(self):
        data = CollectedData(
            device_brand="Samsung",
            device_model="Galaxy S24",
            problem_category="screen_replacement",
        )
        dump = data.model_dump(exclude_none=True)
        assert "device_brand" in dump
        assert "customer_name" not in dump

    def test_full_data(self):
        data = CollectedData(
            device_category="smartphone",
            device_brand="Apple",
            device_model="iPhone 15 Pro",
            problem_raw="разбил экран",
            problem_category="screen_replacement",
            problem_description="Разбит экран, сенсор не работает",
            urgency="urgent",
            has_previous_repair=False,
            customer_name="Михаил",
            customer_phone="+79035551234",
            estimated_price_min=8900.0,
            estimated_price_max=14500.0,
            price_confidence="high",
        )
        assert data.device_brand == "Apple"
        assert data.estimated_price_min == 8900.0


class TestSessionManager:
    """Test SessionManager with mock Redis."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, session_manager, mock_redis):
        state = SessionState(
            conversation_id="conv-1",
            shop_id="shop-1",
        )
        await session_manager.save("shop-1", "user-1", state)
        mock_redis.setex.assert_called_once()

        # Verify key format
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == "session:shop-1:user-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, session_manager):
        result = await session_manager.get("shop-1", "unknown-user")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, session_manager, mock_redis):
        await session_manager.delete("shop-1", "user-1")
        mock_redis.delete.assert_called_once_with("session:shop-1:user-1")
