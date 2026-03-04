"""InBuild constants — service categories, property types, keyboards."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ── Service category selection keyboard ──
SERVICE_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 Ремонт под ключ", callback_data="service:full_renovation"),
            InlineKeyboardButton(text="🔨 Частичный ремонт", callback_data="service:partial_renovation"),
        ],
        [
            InlineKeyboardButton(text="🚿 Сантехника", callback_data="service:plumbing"),
            InlineKeyboardButton(text="⚡ Электрика", callback_data="service:electrical"),
        ],
        [
            InlineKeyboardButton(text="🎨 Покраска / штукатурка", callback_data="service:painting"),
            InlineKeyboardButton(text="🪟 Окна / двери", callback_data="service:windows_doors"),
        ],
        [
            InlineKeyboardButton(text="🏗️ Кровля / фасад", callback_data="service:roofing_facade"),
            InlineKeyboardButton(text="📐 Дизайн-проект", callback_data="service:design"),
        ],
        [
            InlineKeyboardButton(text="💬 Другое — опишу", callback_data="service:other"),
        ],
    ]
)

# ── Property type keyboard ──
PROPERTY_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🏢 Квартира", callback_data="property:apartment"),
            InlineKeyboardButton(text="🏠 Дом / коттедж", callback_data="property:house"),
        ],
        [
            InlineKeyboardButton(text="🏬 Коммерческое", callback_data="property:commercial"),
            InlineKeyboardButton(text="🏗️ Новостройка", callback_data="property:new_build"),
        ],
    ]
)

# ── Scope keyboard ──
SCOPE_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Под ключ", callback_data="scope:full"),
            InlineKeyboardButton(text="Частичный", callback_data="scope:partial"),
        ],
        [
            InlineKeyboardButton(text="Косметический", callback_data="scope:cosmetic"),
            InlineKeyboardButton(text="Конкретные работы", callback_data="scope:specific"),
        ],
    ]
)

# ── Timeline keyboard ──
TIMELINE_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Как можно скорее", callback_data="timeline:asap"),
            InlineKeyboardButton(text="В течение месяца", callback_data="timeline:1_month"),
        ],
        [
            InlineKeyboardButton(text="В течение 3 месяцев", callback_data="timeline:3_months"),
            InlineKeyboardButton(text="Пока планирую", callback_data="timeline:flexible"),
        ],
    ]
)

# Human-readable labels for callbacks
SERVICE_LABELS = {
    "full_renovation": "Ремонт под ключ",
    "partial_renovation": "Частичный ремонт",
    "plumbing": "Сантехника",
    "electrical": "Электрика",
    "painting": "Покраска / штукатурка",
    "windows_doors": "Окна / двери",
    "roofing_facade": "Кровля / фасад",
    "design": "Дизайн-проект",
    "other": "Другое",
}

PROPERTY_LABELS = {
    "apartment": "Квартира",
    "house": "Дом / коттедж",
    "commercial": "Коммерческое помещение",
    "new_build": "Новостройка",
}

SCOPE_LABELS = {
    "full": "Под ключ",
    "partial": "Частичный ремонт",
    "cosmetic": "Косметический ремонт",
    "specific": "Конкретные работы",
}

TIMELINE_LABELS = {
    "asap": "Как можно скорее",
    "1_month": "В течение месяца",
    "3_months": "В течение 3 месяцев",
    "flexible": "Пока планирую",
}
