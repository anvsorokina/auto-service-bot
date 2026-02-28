"""Base class for conversation steps."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from aiogram.types import InlineKeyboardMarkup

from src.schemas.conversation import SessionState


@dataclass
class StepResult:
    """Result of processing a conversation step."""

    response_text: str
    keyboard: Optional[InlineKeyboardMarkup] = None
    next_step: Optional[str] = None  # None = stay on current step
    update_data: Optional[dict] = None  # fields to update in CollectedData
    intent: Optional[str] = None  # "provide_data", "question", "off_topic", etc.


class BaseStep(ABC):
    """Abstract base class for all conversation steps."""

    @abstractmethod
    async def process(self, user_message: str, state: SessionState) -> StepResult:
        """Process user input and return response with next step.

        Args:
            user_message: The message text from the user
            state: Current session state

        Returns:
            StepResult with response and optional state changes
        """
        ...

    @abstractmethod
    async def get_initial_message(self, state: SessionState) -> StepResult:
        """Get the initial prompt for this step (when entering it).

        Args:
            state: Current session state

        Returns:
            StepResult with the initial prompt and keyboard
        """
        ...
