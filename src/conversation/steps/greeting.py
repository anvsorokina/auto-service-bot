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

        # Helper: collect any problem fields the LLM extracted
        def _problem_fields(src: dict) -> dict:
            fields = {}
            if src.get("problem_category"):
                fields["problem_category"] = src["problem_category"]
            if src.get("problem_description"):
                fields["problem_description"] = src["problem_description"]
            if src.get("urgency_hint") or src.get("urgency"):
                fields["urgency"] = src.get("urgency_hint") or src.get("urgency")
            return fields

        # ── Case 1: brand + model both known ──────────────────────────
        if parsed.get("device_brand") and parsed.get("device_model"):
            update = {
                "device_category": parsed.get("device_category", "car"),
                "device_brand": parsed["device_brand"],
                "device_model": parsed["device_model"],
            }
            problem = _problem_fields(parsed)
            update.update(problem)

            # If problem is known too → skip straight to estimate
            if problem.get("problem_category"):
                return StepResult(
                    response_text=result.response_text,
                    next_step=ConversationStep.ESTIMATE.value,
                    update_data=update,
                    intent=result.intent,
                )
            # Brand + model, no problem → ask about the problem
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.PROBLEM.value,
                update_data=update,
                intent=result.intent,
            )

        # ── Case 2: brand only (no model) ─────────────────────────────
        if parsed.get("device_brand"):
            update = {
                "device_category": parsed.get("device_category", "car"),
                "device_brand": parsed["device_brand"],
            }
            problem = _problem_fields(parsed)
            update.update(problem)

            # Brand + problem known → skip model, go to estimate
            if problem.get("problem_category"):
                return StepResult(
                    response_text=result.response_text,
                    next_step=ConversationStep.ESTIMATE.value,
                    update_data=update,
                    intent=result.intent,
                )
            # Brand only → ask for model
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.DEVICE_MODEL.value,
                update_data=update,
                intent=result.intent,
            )

        # ── Case 3: no brand found — save any problem data and show buttons ──
        # This handles "у меня стартер не крутит": we save the problem description
        # so that when the user types the car brand on the NEXT message the engine
        # already has problem_description / problem_category in collected data.
        problem = _problem_fields(parsed)
        # Also preserve problem info that may already be in collected state
        # (carry-over from a previous incomplete extraction)
        update_data = problem if problem else None

        return StepResult(
            response_text=result.response_text,
            keyboard=CAR_BRAND_KEYBOARD,
            update_data=update_data,
            intent=result.intent,
        )
