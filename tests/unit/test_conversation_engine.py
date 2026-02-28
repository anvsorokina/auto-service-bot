"""Tests for conversation engine — message routing and state management."""

import pytest
from unittest.mock import AsyncMock, patch

from src.conversation.engine import ConversationEngine
from src.schemas.conversation import ConversationStep


class TestConversationEngine:
    """Test engine message handling."""

    @pytest.mark.asyncio
    async def test_start_creates_new_session(self, engine: ConversationEngine):
        result = await engine.handle_message(
            shop_id="shop-1",
            user_id="user-1",
            message_text="/start",
        )
        assert result.response_text
        assert "помощник" in result.response_text.lower() or "ремонт" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_master_command_resets(self, engine: ConversationEngine):
        result = await engine.handle_message(
            shop_id="shop-1",
            user_id="user-1",
            message_text="мастер",
        )
        assert "мастер" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_callback_device_selection(self, engine: ConversationEngine, mock_redis):
        # First create a session
        mock_redis.get = AsyncMock(return_value=None)
        await engine.handle_message(
            shop_id="shop-1",
            user_id="user-1",
            message_text="/start",
        )

        # Now mock that session exists
        from src.schemas.conversation import SessionState, CollectedData
        state = SessionState(
            conversation_id="conv-1",
            shop_id="shop-1",
            current_step=ConversationStep.GREETING,
            collected=CollectedData(),
        )
        mock_redis.get = AsyncMock(return_value=state.model_dump_json())

        result = await engine.handle_callback(
            shop_id="shop-1",
            user_id="user-1",
            callback_data="device:smartphone",
        )
        assert result.response_text
        assert result.keyboard is not None  # Should show brand buttons

    @pytest.mark.asyncio
    async def test_callback_no_session(self, engine: ConversationEngine):
        result = await engine.handle_callback(
            shop_id="shop-1",
            user_id="user-1",
            callback_data="device:smartphone",
        )
        assert "истекла" in result.response_text.lower() or "start" in result.response_text.lower()
