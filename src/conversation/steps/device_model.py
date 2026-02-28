"""Device model step — car model and year identification."""

from src.conversation.steps.base import BaseStep, StepResult
from src.llm.unified import process_message
from src.schemas.conversation import ConversationStep, SessionState


class DeviceModelStep(BaseStep):
    """Handle specific car model (and optionally year) input."""

    async def get_initial_message(self, state: SessionState) -> StepResult:
        """Ask the user for their car model and year."""
        brand = state.collected.device_brand or "автомобиля"
        return StepResult(
            response_text=f"Напишите модель вашего {brand} (и год, если знаете):",
        )

    async def process(self, user_message: str, state: SessionState) -> StepResult:
        """Parse car model (and year) from free text."""
        result = await process_message(
            user_message=user_message,
            step="device_model",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        parsed = result.parsed_data
        model = parsed.get("device_model")

        # If LLM couldn't extract a model (user doesn't know it) — that's ok, move on
        if not model or model.lower() in ("не знаю", "unknown", "не указана", "null"):
            model = None

        # Only stay on this step for genuine off-topic questions (not "I don't know")
        if result.intent == "off_topic" and not result.should_advance:
            return StepResult(
                response_text=result.response_text,
                intent=result.intent,
            )

        # Always advance — model is optional, the mechanic can clarify on-site
        return StepResult(
            response_text=result.response_text,
            next_step=ConversationStep.PROBLEM.value,
            update_data={
                "device_model": model,
                "device_category": parsed.get("device_category") or state.collected.device_category or "car",
            },
            intent="provide_data",
        )
