"""Service type step — clarify what construction/renovation work is needed."""

from src.products.inbuild.llm import process_build_message
from src.products.inbuild.schemas import BuildSessionState, BuildStep
from src.products.inbuild.steps.base import BuildBaseStep, BuildStepResult


class ServiceTypeStep(BuildBaseStep):
    """Collect a detailed description of the required construction work."""

    async def get_initial_message(self, state: BuildSessionState) -> BuildStepResult:
        """Ask the customer to describe the scope of work."""
        return BuildStepResult(
            response_text="Расскажите подробнее — какие работы нужны?",
        )

    async def process(self, user_message: str, state: BuildSessionState) -> BuildStepResult:
        """Parse service description using construction LLM."""
        result = await process_build_message(
            user_message=user_message,
            step="service_type",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return BuildStepResult(
                response_text=result.response_text,
                intent=result.intent,
            )

        parsed = result.parsed_data
        update: dict = {}

        if parsed.get("service_category"):
            update["service_category"] = parsed["service_category"]
        if parsed.get("service_description"):
            update["service_description"] = parsed["service_description"]

        # Fall back to raw message if LLM returned nothing useful
        if not update.get("service_description"):
            update["service_description"] = user_message.strip()

        return BuildStepResult(
            response_text=result.response_text,
            next_step=BuildStep.PROPERTY_INFO.value,
            update_data=update,
            intent=result.intent,
        )
