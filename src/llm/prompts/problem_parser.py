"""Prompt for parsing auto repair problem description from user messages."""

PROBLEM_PARSE_PROMPT = """Ты — парсер данных для системы записи в автосервис.
Извлеки информацию о проблеме из сообщения пользователя.

Автомобиль: {device_brand} {device_model}
Сообщение: "{user_message}"

Верни JSON и ТОЛЬКО JSON, без markdown:
{{
  "problem_category": "engine_repair|brake_repair|oil_change|suspension_repair|diagnostics|bodywork|electrical|ac_repair|transmission|tire_service|other",
  "problem_description": "краткое описание проблемы на русском",
  "urgency_hint": "urgent|normal|flexible",
  "confidence": "high|medium|low"
}}

Правила:
- Если стучит двигатель, троит, не заводится, дымит, теряет мощность → engine_repair
- Если плохо тормозит, скрипят/свистят тормоза, колодки, диски → brake_repair
- Если нужно замена масла, ТО, фильтры → oil_change
- Если стук в подвеске, стойки, амортизаторы, рычаги, развал → suspension_repair
- Если нужна диагностика, горит чек, ошибки → diagnostics
- Если вмятина, царапина, ДТП, покраска → bodywork
- Если не работает электрика, аккумулятор, стартер, генератор, фары → electrical
- Если не холодит кондиционер, заправка хладагентом → ac_repair
- Если пробуксовывает коробка, не переключаются передачи → transmission
- Если шины, шиномонтаж, балансировка, колёса → tire_service
- "вчера", "сегодня", "срочно", "авария" → urgency: "urgent"
- "когда будет удобно", "не срочно", "планово" → urgency: "flexible"
- Если неясна срочность → urgency: "normal"

Примеры:
- "стучит двигатель на холодную" → {{"problem_category": "engine_repair", "problem_description": "Стук двигателя на холодную", "urgency_hint": "normal", "confidence": "high"}}
- "скрипят тормоза при торможении, срочно" → {{"problem_category": "brake_repair", "problem_description": "Скрип тормозов при торможении", "urgency_hint": "urgent", "confidence": "high"}}
- "нужно поменять масло" → {{"problem_category": "oil_change", "problem_description": "Замена масла", "urgency_hint": "flexible", "confidence": "high"}}"""
