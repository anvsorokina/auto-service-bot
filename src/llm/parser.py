"""LLM parser — extracts structured data from free text."""

from __future__ import annotations

import json

import structlog

from src.config import settings
from src.llm.client import get_llm_client
from src.llm.prompts.device_parser import DEVICE_PARSE_PROMPT
from src.llm.prompts.problem_parser import PROBLEM_PARSE_PROMPT

logger = structlog.get_logger()


async def parse_device_info(user_message: str) -> dict:
    """Parse device info from user message using LLM.

    Returns: {"device_category", "device_brand", "device_model", "confidence"}
    """
    client = get_llm_client()

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": DEVICE_PARSE_PROMPT.format(user_message=user_message),
                }
            ],
        )
        text = response.content[0].text.strip()
        # Handle potential markdown wrapping
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result = json.loads(text)
        logger.info("device_parsed", result=result, tokens=response.usage.input_tokens)
        return result

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("device_parse_failed", error=str(e), message=user_message)
        return {
            "device_category": "unknown",
            "device_brand": None,
            "device_model": None,
            "confidence": "low",
        }


async def parse_problem_info(
    user_message: str,
    device_brand: str | None = None,
    device_model: str | None = None,
) -> dict:
    """Parse problem description from user message using LLM.

    Returns: {"problem_category", "problem_description", "urgency_hint", "confidence"}
    """
    client = get_llm_client()

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": PROBLEM_PARSE_PROMPT.format(
                        user_message=user_message,
                        device_brand=device_brand or "неизвестный",
                        device_model=device_model or "неизвестная модель",
                    ),
                }
            ],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result = json.loads(text)
        logger.info("problem_parsed", result=result)
        return result

    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning("problem_parse_failed", error=str(e), message=user_message)
        return {
            "problem_category": "other",
            "problem_description": user_message,
            "urgency_hint": "normal",
            "confidence": "low",
        }


async def parse_contact_info(user_message: str) -> dict:
    """Parse name and phone from user message using LLM.

    Returns: {"name", "phone"}
    """
    client = get_llm_client()

    prompt = f"""Извлеки имя и/или телефон из сообщения.
Сообщение: "{user_message}"

Верни JSON: {{"name": "имя или null", "phone": "телефон или null"}}
Нормализуй телефон в формат +7XXXXXXXXXX если это российский номер.
Верни ТОЛЬКО JSON."""

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(text)

    except Exception as e:
        logger.warning("contact_parse_failed", error=str(e))
        return {"name": user_message.strip(), "phone": None}
