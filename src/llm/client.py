"""Anthropic async client singleton."""

from __future__ import annotations

from anthropic import AsyncAnthropic

from src.config import settings

_client: AsyncAnthropic | None = None


def get_llm_client() -> AsyncAnthropic:
    """Get or create the Anthropic async client."""
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client
