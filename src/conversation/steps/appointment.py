"""Appointment step — schedule a visit."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.conversation.steps.base import BaseStep, StepResult
from src.schemas.conversation import ConversationStep, SessionState


class AppointmentStep(BaseStep):
    """Handle appointment scheduling."""

    async def get_initial_message(self, state: SessionState) -> StepResult:
        """Show time slot selection."""
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Сегодня", callback_data="time:today"),
                    InlineKeyboardButton(text="Завтра", callback_data="time:tomorrow"),
                ],
                [
                    InlineKeyboardButton(
                        text="Другой день", callback_data="time:custom"
                    ),
                ],
            ]
        )
        return StepResult(
            response_text="Когда вам удобно приехать?",
            keyboard=keyboard,
        )

    async def process(self, user_message: str, state: SessionState) -> StepResult:
        """Parse appointment time from user input.

        After selecting time, move to CONTACT_INFO to collect name + phone.
        """
        response = (
            f"Отлично, записываю на {user_message}!\n\n"
            "Как к вам обращаться?"
        )

        return StepResult(
            response_text=response,
            next_step=ConversationStep.CONTACT_INFO.value,
            update_data={"preferred_time": user_message},
        )
