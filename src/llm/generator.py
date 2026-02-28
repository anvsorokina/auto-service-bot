"""LLM response generator — creates natural bot responses."""

import structlog

from src.config import settings
from src.llm.client import get_llm_client
from src.llm.prompts.response_generator import RESPONSE_GENERATE_PROMPT
from src.schemas.conversation import CollectedData

logger = structlog.get_logger()


async def generate_response(
    step: str,
    task: str,
    collected_data: CollectedData,
    shop_name: str = "",
    language: str = "ru",
) -> str:
    """Generate a natural bot response using LLM.

    Args:
        step: Current conversation step name
        task: What the response should achieve
        collected_data: Data collected so far
        shop_name: Name of the shop
        language: Response language

    Returns:
        Generated response text
    """
    client = get_llm_client()

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": RESPONSE_GENERATE_PROMPT.format(
                        shop_name=shop_name,
                        language=language,
                        step=step,
                        collected_data=collected_data.model_dump_json(exclude_none=True),
                        task=task,
                    ),
                }
            ],
        )
        text = response.content[0].text.strip()
        logger.info(
            "response_generated",
            step=step,
            tokens=response.usage.output_tokens,
            length=len(text),
        )
        return text

    except Exception as e:
        logger.error("response_generation_failed", error=str(e), step=step)
        # Fallback responses
        fallback = {
            "greeting": "Привет! Расскажите, какое устройство нужно отремонтировать?",
            "device_type": "Какое у вас устройство?",
            "device_model": "Какая модель?",
            "problem": "Что случилось с устройством?",
            "contact_info": "Как вас зовут?",
        }
        return fallback.get(step, "Произошла ошибка. Попробуйте ещё раз или напишите 'мастер'.")
