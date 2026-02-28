"""Problem step — identify what's wrong with the car."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.conversation.steps.base import BaseStep, StepResult
from src.llm.unified import process_message
from src.schemas.conversation import ConversationStep, SessionState

# Auto repair problem category buttons — shown for all cars
AUTO_PROBLEM_BUTTONS = [
    [
        InlineKeyboardButton(text="Двигатель", callback_data="problem:engine_repair"),
        InlineKeyboardButton(text="Тормоза", callback_data="problem:brake_repair"),
    ],
    [
        InlineKeyboardButton(text="Замена масла / ТО", callback_data="problem:oil_change"),
        InlineKeyboardButton(text="Подвеска", callback_data="problem:suspension_repair"),
    ],
    [
        InlineKeyboardButton(text="Диагностика", callback_data="problem:diagnostics"),
        InlineKeyboardButton(text="Электрика", callback_data="problem:electrical"),
    ],
    [
        InlineKeyboardButton(text="Кузов / покраска", callback_data="problem:bodywork"),
        InlineKeyboardButton(text="Кондиционер", callback_data="problem:ac_repair"),
    ],
    [
        InlineKeyboardButton(text="Коробка передач", callback_data="problem:transmission"),
        InlineKeyboardButton(text="Шины / колёса", callback_data="problem:tire_service"),
    ],
    [
        InlineKeyboardButton(text="Другое — опишу", callback_data="problem:custom"),
    ],
]


class ProblemStep(BaseStep):
    """Handle problem description and classification."""

    async def get_initial_message(self, state: SessionState) -> StepResult:
        """Show auto repair category selection."""
        car = state.collected.device_model or state.collected.device_brand or "автомобилем"
        return StepResult(
            response_text=f"Что случилось с {car}?",
            keyboard=InlineKeyboardMarkup(inline_keyboard=AUTO_PROBLEM_BUTTONS),
        )

    async def process(self, user_message: str, state: SessionState) -> StepResult:
        """Parse problem from free text using unified LLM."""
        result = await process_message(
            user_message=user_message,
            step="problem",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        parsed = result.parsed_data

        # If LLM extracted a problem description — advance even if intent was misclassified
        has_problem_data = parsed.get("problem_description") or parsed.get("problem_category")

        if result.intent in ("question", "off_topic") and not has_problem_data:
            return StepResult(
                response_text=result.response_text,
                keyboard=InlineKeyboardMarkup(inline_keyboard=AUTO_PROBLEM_BUTTONS),
                intent=result.intent,
            )

        update_data = {
            "problem_raw": user_message,
            "problem_category": parsed.get("problem_category", "other"),
            "problem_description": parsed.get("problem_description", user_message),
        }

        if parsed.get("urgency_hint") == "urgent":
            update_data["urgency"] = "urgent"

        return StepResult(
            response_text=result.response_text,
            next_step=ConversationStep.ESTIMATE.value,
            update_data=update_data,
            intent="provide_data",
        )
