"""Base class for InBuild conversation steps."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from aiogram.types import InlineKeyboardMarkup

from src.products.inbuild.schemas import BuildSessionState


@dataclass
class BuildStepResult:
    """Result of processing a construction conversation step."""

    response_text: str
    keyboard: Optional[InlineKeyboardMarkup] = None
    next_step: Optional[str] = None  # None = stay on current step
    update_data: Optional[dict] = None  # fields to update in BuildCollectedData
    intent: Optional[str] = None  # "provide_data", "question", "off_topic", etc.


class BuildBaseStep(ABC):
    """Abstract base class for all InBuild conversation steps."""

    @abstractmethod
    async def process(self, user_message: str, state: BuildSessionState) -> BuildStepResult:
        """Process user input and return response with next step.

        Args:
            user_message: The message text from the user
            state: Current build session state

        Returns:
            BuildStepResult with response and optional state changes
        """
        ...

    @abstractmethod
    async def get_initial_message(self, state: BuildSessionState) -> BuildStepResult:
        """Get the initial prompt for this step (when entering it).

        Args:
            state: Current build session state

        Returns:
            BuildStepResult with the initial prompt and keyboard
        """
        ...
