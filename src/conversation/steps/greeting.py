"""Greeting step — initial bot response and intent classification."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.conversation.steps.base import BaseStep, StepResult
from src.llm.unified import current_shop_config, process_message
from src.schemas.conversation import ConversationStep, SessionState

# Car brand keyboard — used as the main entry-point selection
# callback_data prefix "device:" is kept for compatibility with the engine's callback router,
# but values are now car brand names (routed the same way as device categories).
CAR_BRAND_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Toyota", callback_data="device:Toyota"),
            InlineKeyboardButton(text="BMW", callback_data="device:BMW"),
        ],
        [
            InlineKeyboardButton(text="Mercedes", callback_data="device:Mercedes"),
            InlineKeyboardButton(text="Hyundai", callback_data="device:Hyundai"),
        ],
        [
            InlineKeyboardButton(text="Kia", callback_data="device:Kia"),
            InlineKeyboardButton(text="Volkswagen", callback_data="device:Volkswagen"),
        ],
        [
            InlineKeyboardButton(text="Lada / ВАЗ", callback_data="device:Lada"),
            InlineKeyboardButton(text="Другая марка", callback_data="device:other"),
        ],
    ]
)

# Keep backward-compatible alias so any code that imports DEVICE_KEYBOARD still works
DEVICE_KEYBOARD = CAR_BRAND_KEYBOARD


class GreetingStep(BaseStep):
    """Handles /start and initial greeting."""

    async def get_initial_message(self, state: SessionState) -> StepResult:
        """Show greeting with car brand selection.

        Uses custom greeting from shop_config if available.
        """
        # Check for custom greeting from shop settings
        config = current_shop_config.get()
        custom_greeting = config.get("greeting_text") if config else None

        if custom_greeting:
            text = custom_greeting
        else:
            text = (
                "Привет! Я Алекс, помогу с ремонтом автомобиля.\n\n"
                "Расскажите, что случилось — или выберите марку машины ниже."
            )
        return StepResult(
            response_text=text,
            keyboard=CAR_BRAND_KEYBOARD,
            next_step=ConversationStep.DEVICE_TYPE.value,
        )

    async def process(self, user_message: str, state: SessionState) -> StepResult:
        """Process free text — try to extract car brand/model directly."""
        result = await process_message(
            user_message=user_message,
            step="greeting",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return StepResult(
                response_text=result.response_text,
                keyboard=CAR_BRAND_KEYBOARD,
                intent=result.intent,
            )

        parsed = result.parsed_data

        # User gave full brand + model info
        if parsed.get("device_model") and parsed.get("device_brand"):
            update = {
                "device_category": parsed.get("device_category", "car"),
                "device_brand": parsed["device_brand"],
                "device_model": parsed["device_model"],
            }
            # If problem was also mentioned, grab it too
            if parsed.get("problem_category"):
                update["problem_category"] = parsed["problem_category"]
                update["problem_description"] = parsed.get("problem_description", "")
                return StepResult(
                    response_text=result.response_text,
                    next_step=ConversationStep.CONTACT_INFO.value,
                    update_data=update,
                    intent=result.intent,
                )
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.PROBLEM.value,
                update_data=update,
                intent=result.intent,
            )

        # Got brand but not model
        if parsed.get("device_brand"):
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.DEVICE_MODEL.value,
                update_data={
                    "device_category": parsed.get("device_category", "car"),
                    "device_brand": parsed["device_brand"],
                },
                intent=result.intent,
            )

        # Didn't understand — show buttons with LLM response
        return StepResult(
            response_text=result.response_text,
            keyboard=CAR_BRAND_KEYBOARD,
            intent=result.intent,
        )
