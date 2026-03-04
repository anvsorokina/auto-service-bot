"""Estimate step — show price estimate and route based on customer decision."""

from src.products.inbuild.llm import process_build_message
from src.products.inbuild.schemas import BuildSessionState, BuildStep
from src.products.inbuild.steps.base import BuildBaseStep, BuildStepResult


class BuildEstimateStep(BuildBaseStep):
    """Show price estimate and handle the customer's response."""

    async def get_initial_message(self, state: BuildSessionState) -> BuildStepResult:
        """Display price estimate in USD if available."""
        collected = state.collected

        if collected.estimated_price_min and collected.estimated_price_max:
            price_min = collected.estimated_price_min
            price_max = collected.estimated_price_max
            currency = collected.budget_currency or "USD"

            if currency == "USD":
                price_str = f"${price_min:,.0f} – ${price_max:,.0f}"
            else:
                price_str = f"{price_min:,.0f} – {price_max:,.0f} {currency}"

            duration_note = ""
            if collected.estimated_duration_days:
                duration_note = (
                    f"\nОриентировочный срок: {collected.estimated_duration_days} дн."
                )

            confidence_note = ""
            if collected.price_confidence == "low":
                confidence_note = "\nТочную стоимость специалист уточнит после осмотра."

            text = (
                f"Ориентировочная стоимость: {price_str}"
                f"{duration_note}"
                f"{confidence_note}\n\n"
                "Хотите записаться на консультацию или вызвать специалиста для замера?"
            )
            return BuildStepResult(response_text=text)

        # No estimate available yet — LLM response carries the conversation
        return BuildStepResult(response_text="")

    async def process(self, user_message: str, state: BuildSessionState) -> BuildStepResult:
        """Handle customer decision after seeing the estimate."""
        result = await process_build_message(
            user_message=user_message,
            step="estimate",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return BuildStepResult(
                response_text=result.response_text,
                intent=result.intent,
            )

        parsed = result.parsed_data
        decision = parsed.get("decision", "")

        if decision == "appointment" or result.intent == "confirm":
            # Customer wants to schedule a consultation → collect contacts
            return BuildStepResult(
                response_text=result.response_text,
                next_step=BuildStep.CONTACT_INFO.value,
                intent=result.intent,
            )
        elif decision == "call_master":
            # Wants a specialist to come → collect contacts as well
            return BuildStepResult(
                response_text=result.response_text,
                next_step=BuildStep.CONTACT_INFO.value,
                intent=result.intent,
            )
        else:
            # Thinking / declining → wrap up
            return BuildStepResult(
                response_text=result.response_text,
                next_step=BuildStep.COMPLETED.value,
                intent=result.intent,
            )
