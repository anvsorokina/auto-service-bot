"""Timeline and budget step — collect timing and budget constraints."""

from src.products.inbuild.constants import TIMELINE_KEYBOARD
from src.products.inbuild.llm import process_build_message
from src.products.inbuild.schemas import BuildSessionState, BuildStep
from src.products.inbuild.steps.base import BuildBaseStep, BuildStepResult


class TimelineBudgetStep(BuildBaseStep):
    """Collect project timeline and budget range from the customer."""

    async def get_initial_message(self, state: BuildSessionState) -> BuildStepResult:
        """Ask when the project should start and what budget is expected."""
        return BuildStepResult(
            response_text=(
                "Когда планируете начать и какой бюджет рассматриваете?\n"
                "Выберите сроки или напишите своими словами."
            ),
            keyboard=TIMELINE_KEYBOARD,
        )

    async def process(self, user_message: str, state: BuildSessionState) -> BuildStepResult:
        """Parse timeline and budget using construction LLM."""
        result = await process_build_message(
            user_message=user_message,
            step="timeline_budget",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return BuildStepResult(
                response_text=result.response_text,
                keyboard=TIMELINE_KEYBOARD,
                intent=result.intent,
            )

        parsed = result.parsed_data
        update: dict = {}

        if parsed.get("budget_min") is not None:
            update["budget_min"] = parsed["budget_min"]
        if parsed.get("budget_max") is not None:
            update["budget_max"] = parsed["budget_max"]
        if parsed.get("budget_currency"):
            update["budget_currency"] = parsed["budget_currency"]
        if parsed.get("timeline"):
            update["timeline"] = parsed["timeline"]
        if parsed.get("preferred_start_date"):
            update["preferred_start_date"] = parsed["preferred_start_date"]

        return BuildStepResult(
            response_text=result.response_text,
            next_step=BuildStep.ESTIMATE.value,
            update_data=update or None,
            intent=result.intent,
        )
