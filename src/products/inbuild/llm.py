"""InBuild LLM module — construction-specific parsing + response generation."""

from __future__ import annotations

import contextvars
import json
from dataclasses import dataclass, field
from typing import Optional

import structlog

from src.config import settings
from src.llm.client import get_llm_client
from src.llm.safety import (
    INJECTION_RESPONSE,
    SYSTEM_PROMPT,
    detect_injection,
    detect_suspicious,
)
from src.products.inbuild.prompts import build_construction_prompt

logger = structlog.get_logger()

current_build_shop_config: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "current_build_shop_config", default=None
)


@dataclass
class BuildLLMResult:
    """Result from construction LLM processing."""
    intent: str = "provide_data"
    parsed_data: dict = field(default_factory=dict)
    response_text: str = ""
    should_advance: bool = False
    confidence: str = "low"


BUILD_FALLBACK_RESPONSES = {
    "greeting": "Какие работы вас интересуют?",
    "service_type": "Расскажите подробнее о нужных работах.",
    "property_info": "Расскажите об объекте — квартира, дом, коммерческое?",
    "project_desc": "Опишите, что нужно сделать.",
    "timeline_budget": "Когда планируете начать ремонт?",
    "estimate": "Хотите записаться на осмотр объекта?",
    "contact_info": "Как к вам обращаться?",
}


async def process_build_message(
    user_message: str,
    step: str,
    collected_data: dict,
    message_history: Optional[list[dict]] = None,
    shop_config: Optional[dict] = None,
) -> BuildLLMResult:
    """Process user message for construction conversations."""
    # Safety: prompt injection filter
    injection = detect_injection(user_message)
    if injection:
        return BuildLLMResult(
            intent="off_topic",
            parsed_data={},
            response_text=INJECTION_RESPONSE,
            should_advance=False,
            confidence="high",
        )
    detect_suspicious(user_message)

    client = get_llm_client()
    effective_config = shop_config or current_build_shop_config.get()

    prompt = build_construction_prompt(
        step=step,
        user_message=user_message,
        collected_data=collected_data,
        message_history=message_history or [],
        shop_config=effective_config,
    )

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result_json = json.loads(text)

        logger.info(
            "build_llm_processed",
            step=step,
            intent=result_json.get("intent"),
            confidence=result_json.get("confidence"),
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
        )

        return BuildLLMResult(
            intent=result_json.get("intent", "provide_data"),
            parsed_data=result_json.get("parsed_data", {}),
            response_text=result_json.get("response", BUILD_FALLBACK_RESPONSES.get(step, "")),
            should_advance=result_json.get("should_advance", False),
            confidence=result_json.get("confidence", "low"),
        )

    except json.JSONDecodeError as e:
        logger.warning("build_llm_json_error", error=str(e), step=step)
        return BuildLLMResult(
            intent="provide_data",
            parsed_data={},
            response_text=BUILD_FALLBACK_RESPONSES.get(step, "Не совсем понял. Попробуйте ещё раз."),
            should_advance=False,
            confidence="low",
        )

    except Exception as e:
        logger.error("build_llm_error", error=str(e), step=step)
        return BuildLLMResult(
            intent="provide_data",
            parsed_data={},
            response_text=BUILD_FALLBACK_RESPONSES.get(step, "Не совсем понял. Попробуйте ещё раз."),
            should_advance=False,
            confidence="low",
        )
