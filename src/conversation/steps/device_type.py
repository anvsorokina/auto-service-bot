"""Device type step — car brand selection and popular model shortcuts."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.conversation.steps.base import BaseStep, StepResult
from src.llm.unified import process_message
from src.schemas.conversation import ConversationStep, SessionState

# Popular model keyboards per car brand.
# Each keyboard lets the user pick a well-known model quickly,
# or fall through to free-text input via "Другое".
BRAND_KEYBOARDS: dict[str, list] = {
    "Toyota": [
        [
            InlineKeyboardButton(text="Camry", callback_data="model:Camry"),
            InlineKeyboardButton(text="Corolla", callback_data="model:Corolla"),
        ],
        [
            InlineKeyboardButton(text="RAV4", callback_data="model:RAV4"),
            InlineKeyboardButton(text="Land Cruiser", callback_data="model:Land Cruiser"),
        ],
        [
            InlineKeyboardButton(text="Другая модель — напишу сам", callback_data="model:custom"),
        ],
    ],
    "BMW": [
        [
            InlineKeyboardButton(text="3 серия", callback_data="model:BMW 3 Series"),
            InlineKeyboardButton(text="5 серия", callback_data="model:BMW 5 Series"),
        ],
        [
            InlineKeyboardButton(text="X5", callback_data="model:X5"),
            InlineKeyboardButton(text="X3", callback_data="model:X3"),
        ],
        [
            InlineKeyboardButton(text="Другая модель — напишу сам", callback_data="model:custom"),
        ],
    ],
    "Mercedes": [
        [
            InlineKeyboardButton(text="C-класс", callback_data="model:C-Class"),
            InlineKeyboardButton(text="E-класс", callback_data="model:E-Class"),
        ],
        [
            InlineKeyboardButton(text="GLE", callback_data="model:GLE"),
            InlineKeyboardButton(text="S-класс", callback_data="model:S-Class"),
        ],
        [
            InlineKeyboardButton(text="Другая модель — напишу сам", callback_data="model:custom"),
        ],
    ],
    "Hyundai": [
        [
            InlineKeyboardButton(text="Solaris", callback_data="model:Solaris"),
            InlineKeyboardButton(text="Tucson", callback_data="model:Tucson"),
        ],
        [
            InlineKeyboardButton(text="Creta", callback_data="model:Creta"),
            InlineKeyboardButton(text="Elantra", callback_data="model:Elantra"),
        ],
        [
            InlineKeyboardButton(text="Другая модель — напишу сам", callback_data="model:custom"),
        ],
    ],
    "Kia": [
        [
            InlineKeyboardButton(text="Rio", callback_data="model:Rio"),
            InlineKeyboardButton(text="Sportage", callback_data="model:Sportage"),
        ],
        [
            InlineKeyboardButton(text="Cerato", callback_data="model:Cerato"),
            InlineKeyboardButton(text="Sorento", callback_data="model:Sorento"),
        ],
        [
            InlineKeyboardButton(text="Другая модель — напишу сам", callback_data="model:custom"),
        ],
    ],
    "Volkswagen": [
        [
            InlineKeyboardButton(text="Polo", callback_data="model:Polo"),
            InlineKeyboardButton(text="Tiguan", callback_data="model:Tiguan"),
        ],
        [
            InlineKeyboardButton(text="Passat", callback_data="model:Passat"),
            InlineKeyboardButton(text="Golf", callback_data="model:Golf"),
        ],
        [
            InlineKeyboardButton(text="Другая модель — напишу сам", callback_data="model:custom"),
        ],
    ],
    "Lada": [
        [
            InlineKeyboardButton(text="Vesta", callback_data="model:Vesta"),
            InlineKeyboardButton(text="Granta", callback_data="model:Granta"),
        ],
        [
            InlineKeyboardButton(text="XRAY", callback_data="model:XRAY"),
            InlineKeyboardButton(text="Niva", callback_data="model:Niva"),
        ],
        [
            InlineKeyboardButton(text="Другая модель — напишу сам", callback_data="model:custom"),
        ],
    ],
}

# Fallback keyboard for any brand not listed above
_FALLBACK_KEYBOARD: list = [
    [
        InlineKeyboardButton(text="Написать марку и модель сам", callback_data="model:custom"),
    ]
]


class DeviceTypeStep(BaseStep):
    """Handle car brand selection and show popular models."""

    async def get_initial_message(self, state: SessionState) -> StepResult:
        """Show popular model shortcuts for the selected brand."""
        brand = state.collected.device_brand

        if brand and brand in BRAND_KEYBOARDS:
            keyboard_data = BRAND_KEYBOARDS[brand]
            return StepResult(
                response_text=f"Какая модель {brand}?",
                keyboard=InlineKeyboardMarkup(inline_keyboard=keyboard_data),
            )

        # Unknown brand — just ask for free-text model
        return StepResult(
            response_text=f"Напишите модель вашего {brand or 'автомобиля'}:",
        )

    async def process(self, user_message: str, state: SessionState) -> StepResult:
        """Parse brand (and optionally model) from free text input."""
        result = await process_message(
            user_message=user_message,
            step="device_type",
            collected_data=state.collected.model_dump(),
            message_history=state.message_history,
        )

        if result.intent in ("question", "off_topic"):
            return StepResult(
                response_text=result.response_text,
                keyboard=(await self.get_initial_message(state)).keyboard,
                intent=result.intent,
            )

        parsed = result.parsed_data

        if parsed.get("device_brand"):
            update = {
                "device_brand": parsed["device_brand"],
                "device_category": "car",
            }
            if parsed.get("device_model"):
                update["device_model"] = parsed["device_model"]
                return StepResult(
                    response_text=result.response_text,
                    next_step=ConversationStep.PROBLEM.value,
                    update_data=update,
                    intent=result.intent,
                )
            return StepResult(
                response_text=result.response_text,
                next_step=ConversationStep.DEVICE_MODEL.value,
                update_data=update,
                intent=result.intent,
            )

        # Didn't understand — show keyboard for current brand (or default message)
        return StepResult(
            response_text=result.response_text or "Не совсем понял. Напишите марку автомобиля:",
            keyboard=(await self.get_initial_message(state)).keyboard,
            intent=result.intent,
        )
