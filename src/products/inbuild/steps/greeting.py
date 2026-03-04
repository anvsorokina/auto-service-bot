"""Greeting step — initial bot response for construction intake."""

from src.products.inbuild.constants import SERVICE_KEYBOARD
from src.products.inbuild.llm import process_build_message
from src.products.inbuild.schemas import BuildSessionState, BuildStep
from src.products.inbuild.steps.base import BuildBaseStep, BuildStepResult


class BuildGreetingStep(BuildBaseStep):
    """Handles /start and initial greeting for the construction bot."""

    async def get_initial_message(self, state: BuildSessionState) -> BuildStepResult:
        """Show greeting with service category selection."""
        text = (
            "Привет! Я помогу рассчитать стоимость строительных и ремонтных работ.\n\n"
            "Выберите тип работ или расскажите своими словами — что нужно сделать?"
        )
        return BuildStepResult(
            response_text=text,
            keyboard=SERVICE_KEYBOARD,
            next_step=BuildStep.SERVICE_TYPE.value,
        )

    async def process(self, user_message: str, state: BuildSessionState) -> BuildStepResult:
        """Process free text — try to extract service category directly."""
        result = await process_build_message(
            user_message=user_message,
            step="greeting",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return BuildStepResult(
                response_text=result.response_text,
                keyboard=SERVICE_KEYBOARD,
                intent=result.intent,
            )

        parsed = result.parsed_data
        service_category = parsed.get("service_category")
        service_description = parsed.get("service_description")

        update: dict = {}
        if service_category:
            update["service_category"] = service_category
        if service_description:
            update["service_description"] = service_description

        # If service is already clear — skip SERVICE_TYPE and ask about the property
        if service_category:
            return BuildStepResult(
                response_text=result.response_text,
                next_step=BuildStep.PROPERTY_INFO.value,
                update_data=update or None,
                intent=result.intent,
            )

        # Some info extracted but category still unclear — advance to SERVICE_TYPE
        if service_description:
            return BuildStepResult(
                response_text=result.response_text,
                next_step=BuildStep.SERVICE_TYPE.value,
                update_data=update,
                intent=result.intent,
            )

        # Nothing extracted — show keyboard again
        return BuildStepResult(
            response_text=result.response_text,
            keyboard=SERVICE_KEYBOARD,
            intent=result.intent,
        )
