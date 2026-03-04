"""Contact info step — collect customer name, phone and company."""

from src.products.inbuild.llm import process_build_message
from src.products.inbuild.schemas import BuildSessionState, BuildStep
from src.products.inbuild.steps.base import BuildBaseStep, BuildStepResult


class BuildContactInfoStep(BuildBaseStep):
    """Collect customer name, phone number and optionally company name."""

    async def get_initial_message(self, state: BuildSessionState) -> BuildStepResult:
        """Ask for name, or phone if name is already known."""
        if state.collected.customer_name:
            return BuildStepResult(
                response_text="Оставьте номер телефона для связи:",
            )
        return BuildStepResult(
            response_text="Как к вам обращаться?",
        )

    async def process(self, user_message: str, state: BuildSessionState) -> BuildStepResult:
        """Parse name, phone and company using construction LLM."""
        result = await process_build_message(
            user_message=user_message,
            step="contact_info",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return BuildStepResult(
                response_text=result.response_text,
                intent=result.intent,
            )

        parsed = result.parsed_data

        # If we already have a name — this input is expected to be the phone number
        if state.collected.customer_name and not state.collected.customer_phone:
            phone = (
                parsed.get("customer_phone")
                or parsed.get("phone")
                or user_message.strip()
            )
            update: dict = {"customer_phone": phone}
            if parsed.get("customer_company"):
                update["customer_company"] = parsed["customer_company"]

            return BuildStepResult(
                response_text=result.response_text,
                next_step=BuildStep.COMPLETED.value,
                update_data=update,
                intent=result.intent,
            )

        # First message — extract name (and optionally phone + company)
        name = (
            parsed.get("customer_name")
            or parsed.get("name")
            or user_message.strip()
        )
        phone = parsed.get("customer_phone") or parsed.get("phone")
        company = parsed.get("customer_company")

        update = {"customer_name": name}
        if company:
            update["customer_company"] = company

        if phone:
            update["customer_phone"] = phone
            return BuildStepResult(
                response_text=result.response_text,
                next_step=BuildStep.COMPLETED.value,
                update_data=update,
                intent=result.intent,
            )

        # Got name but no phone — stay on this step so LLM can ask for the phone
        return BuildStepResult(
            response_text=result.response_text,
            update_data=update,
            intent=result.intent,
        )
