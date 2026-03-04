"""Project description step — collect project details, design docs and scope."""

from src.products.inbuild.constants import SCOPE_KEYBOARD
from src.products.inbuild.llm import process_build_message
from src.products.inbuild.schemas import BuildSessionState, BuildStep
from src.products.inbuild.steps.base import BuildBaseStep, BuildStepResult


class ProjectDescriptionStep(BuildBaseStep):
    """Collect project description, design project flag and work scope."""

    async def get_initial_message(self, state: BuildSessionState) -> BuildStepResult:
        """Ask for project details with scope selection keyboard."""
        return BuildStepResult(
            response_text=(
                "Опишите проект подробнее:\n"
                "что именно нужно сделать, есть ли дизайн-проект?"
            ),
            keyboard=SCOPE_KEYBOARD,
        )

    async def process(self, user_message: str, state: BuildSessionState) -> BuildStepResult:
        """Parse project description and scope using construction LLM."""
        result = await process_build_message(
            user_message=user_message,
            step="project_desc",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return BuildStepResult(
                response_text=result.response_text,
                keyboard=SCOPE_KEYBOARD,
                intent=result.intent,
            )

        parsed = result.parsed_data
        update: dict = {}

        if parsed.get("project_description"):
            update["project_description"] = parsed["project_description"]
        if parsed.get("has_design_project") is not None:
            update["has_design_project"] = parsed["has_design_project"]
        if parsed.get("scope"):
            update["scope"] = parsed["scope"]

        # Fall back to raw message as project description if nothing was extracted
        if not update.get("project_description"):
            update["project_description"] = user_message.strip()

        return BuildStepResult(
            response_text=result.response_text,
            next_step=BuildStep.TIMELINE_BUDGET.value,
            update_data=update,
            intent=result.intent,
        )
