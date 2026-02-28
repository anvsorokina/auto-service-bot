"""Contact info step — collect customer name and optionally phone."""

from src.conversation.steps.base import BaseStep, StepResult
from src.llm.unified import process_message
from src.schemas.conversation import ConversationStep, SessionState


class ContactInfoStep(BaseStep):
    """Collect customer name and phone number."""

    async def get_initial_message(self, state: SessionState) -> StepResult:
        """Ask for name."""
        if state.collected.customer_name:
            return StepResult(
                response_text="Оставьте номер телефона для связи (или напишите «пропустить»):",
            )
        return StepResult(
            response_text="Как к вам обращаться?",
        )

    async def process(self, user_message: str, state: SessionState) -> StepResult:
        """Parse name and phone using unified LLM."""
        result = await process_message(
            user_message=user_message,
            step="contact_info",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return StepResult(
                response_text=result.response_text,
                intent=result.intent,
            )

        parsed = result.parsed_data

        # If we already have the name, this input is the phone
        if state.collected.customer_name and not state.collected.customer_phone:
            phone = parsed.get("customer_phone") or parsed.get("phone") or user_message.strip()
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.COMPLETED.value,
                update_data={"customer_phone": phone},
                intent=result.intent,
            )

        # First time — parse name (and maybe phone too)
        name = parsed.get("customer_name") or parsed.get("name") or user_message.strip()
        phone = parsed.get("customer_phone") or parsed.get("phone")

        if phone:
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.COMPLETED.value,
                update_data={"customer_name": name, "customer_phone": phone},
                intent=result.intent,
            )

        # Got name, LLM response should ask for phone
        return StepResult(
            response_text=result.response_text,
            update_data={"customer_name": name},
            intent=result.intent,
        )
