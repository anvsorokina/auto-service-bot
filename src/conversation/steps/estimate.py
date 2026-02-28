"""Estimate step — show price estimate, then handle customer decision via text."""

from src.conversation.steps.base import BaseStep, StepResult
from src.llm.unified import process_message
from src.schemas.conversation import ConversationStep, SessionState


class EstimateStep(BaseStep):
    """Show price estimate and route based on customer's text response."""

    async def get_initial_message(self, state: SessionState) -> StepResult:
        """Show price estimate based on collected data. No buttons — pure text."""
        device = f"{state.collected.device_brand or ''} {state.collected.device_model or ''}".strip()
        problem = state.collected.problem_description or state.collected.problem_category or "ремонт"

        if state.collected.estimated_price_min and state.collected.estimated_price_max:
            price_min = state.collected.estimated_price_min
            price_max = state.collected.estimated_price_max
            text = (
                f"🚗 {device} — {problem}\n\n"
                f"Ориентировочная стоимость: {price_min:,.0f} – {price_max:,.0f} ₽\n\n"
                "Точную цену мастер назовёт после осмотра. "
                "Хотите записаться на приём?"
            )
        else:
            text = (
                f"🚗 {device} — {problem}\n\n"
                "Точную стоимость назовём после диагностики.\n"
                "Компьютерная диагностика от 500 ₽, занимает 20–30 минут.\n\n"
                "Хотите записаться?"
            )

        return StepResult(response_text=text)

    async def process(self, user_message: str, state: SessionState) -> StepResult:
        """Handle free text response to estimate using unified LLM.

        If the customer agrees → move to CONTACT_INFO (ask name + phone).
        If they want a master → handoff (handled by engine's master detection).
        If they want to think → stay in completed.
        """
        result = await process_message(
            user_message=user_message,
            step="estimate",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return StepResult(
                response_text=result.response_text,
                intent=result.intent,
            )

        parsed = result.parsed_data
        decision = parsed.get("decision", "")

        if decision == "appointment" or result.intent == "confirm":
            # Customer agrees → ask for name + phone
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.CONTACT_INFO.value,
                intent=result.intent,
            )
        elif decision == "call_master":
            # Master request (also caught by engine's _is_master_request)
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.COMPLETED.value,
                intent=result.intent,
            )
        else:
            # Think / decline
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.COMPLETED.value,
                intent=result.intent,
            )
