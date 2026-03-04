"""Property info step — collect details about the construction object."""

from src.products.inbuild.constants import PROPERTY_KEYBOARD
from src.products.inbuild.llm import process_build_message
from src.products.inbuild.schemas import BuildSessionState, BuildStep
from src.products.inbuild.steps.base import BuildBaseStep, BuildStepResult


class PropertyInfoStep(BuildBaseStep):
    """Collect property type, area, address and condition."""

    async def get_initial_message(self, state: BuildSessionState) -> BuildStepResult:
        """Ask about the property with quick-select keyboard."""
        return BuildStepResult(
            response_text=(
                "Расскажите об объекте:\n"
                "тип, площадь, адрес и текущее состояние."
            ),
            keyboard=PROPERTY_KEYBOARD,
        )

    async def process(self, user_message: str, state: BuildSessionState) -> BuildStepResult:
        """Parse property details using construction LLM."""
        result = await process_build_message(
            user_message=user_message,
            step="property_info",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return BuildStepResult(
                response_text=result.response_text,
                keyboard=PROPERTY_KEYBOARD,
                intent=result.intent,
            )

        parsed = result.parsed_data
        update: dict = {}

        if parsed.get("property_type"):
            update["property_type"] = parsed["property_type"]
        if parsed.get("property_area_sqm") is not None:
            update["property_area_sqm"] = parsed["property_area_sqm"]
        if parsed.get("property_address"):
            update["property_address"] = parsed["property_address"]
        if parsed.get("property_condition"):
            update["property_condition"] = parsed["property_condition"]

        # Carry over existing property_type from collected data if not overridden
        # (happens when user clicked the keyboard button before typing)
        if not update.get("property_type") and state.collected.property_type:
            update["property_type"] = state.collected.property_type

        return BuildStepResult(
            response_text=result.response_text,
            next_step=BuildStep.PROJECT_DESCRIPTION.value,
            update_data=update or None,
            intent=result.intent,
        )
