"""Unified LLM module — combined parsing + response generation in one call."""

from __future__ import annotations

import contextvars
import json
from dataclasses import dataclass, field
from typing import Optional

import structlog

from src.config import settings
from src.llm.client import get_llm_client
from src.llm.prompts.unified_prompt import build_unified_prompt

logger = structlog.get_logger()

# ContextVar allows engine to set shop_config once,
# and all step handlers' process_message calls will pick it up automatically.
current_shop_config: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "current_shop_config", default=None
)


@dataclass
class UnifiedLLMResult:
    """Result from unified LLM processing."""

    intent: str = "provide_data"
    parsed_data: dict = field(default_factory=dict)
    response_text: str = ""
    should_advance: bool = False
    confidence: str = "low"


# Fallback responses per step when LLM fails
FALLBACK_RESPONSES = {
    "greeting": "Какой автомобиль нужно починить?",
    "device_type": "Какая марка автомобиля?",
    "device_model": "Ничего, разберёмся на месте. Что случилось с машиной?",
    "problem": "Расскажите, что случилось?",
    "contact_info": "Как вас зовут?",
    "estimate": "Хотите записаться на диагностику?",
    "appointment": "Когда удобно приехать?",
}


async def process_message(
    user_message: str,
    step: str,
    collected_data: dict,
    message_history: Optional[list[dict]] = None,
    shop_config: Optional[dict] = None,
) -> UnifiedLLMResult:
    """Process user message with unified parsing + response generation.

    Makes a single LLM call that extracts structured data AND generates
    a natural, contextual response.

    Args:
        user_message: The raw user message text
        step: Current conversation step name
        collected_data: All data collected so far (as dict)
        message_history: Recent conversation history
        shop_config: Shop settings (personality, greeting, promo, FAQ, address)

    Returns:
        UnifiedLLMResult with intent, parsed data, response text, etc.
    """
    client = get_llm_client()

    # Use explicit shop_config, or fall back to ContextVar set by engine
    effective_config = shop_config or current_shop_config.get()

    prompt = build_unified_prompt(
        step=step,
        user_message=user_message,
        collected_data=collected_data,
        message_history=message_history or [],
        shop_config=effective_config,
    )

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Handle potential markdown wrapping
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result_json = json.loads(text)

        logger.info(
            "unified_llm_processed",
            step=step,
            intent=result_json.get("intent"),
            confidence=result_json.get("confidence"),
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
        )

        return UnifiedLLMResult(
            intent=result_json.get("intent", "provide_data"),
            parsed_data=result_json.get("parsed_data", {}),
            response_text=result_json.get("response", FALLBACK_RESPONSES.get(step, "")),
            should_advance=result_json.get("should_advance", False),
            confidence=result_json.get("confidence", "low"),
        )

    except json.JSONDecodeError as e:
        logger.warning(
            "unified_llm_json_error",
            error=str(e),
            step=step,
            raw_text=text[:200] if 'text' in dir() else "no response",
        )
        # Try to extract just the response text from non-JSON output
        return UnifiedLLMResult(
            intent="provide_data",
            parsed_data={},
            response_text=FALLBACK_RESPONSES.get(step, "Не совсем понял. Попробуйте ещё раз."),
            should_advance=False,
            confidence="low",
        )

    except Exception as e:
        logger.error("unified_llm_error", error=str(e), step=step)
        return UnifiedLLMResult(
            intent="provide_data",
            parsed_data={},
            response_text=FALLBACK_RESPONSES.get(step, "Не совсем понял. Попробуйте ещё раз."),
            should_advance=False,
            confidence="low",
        )
