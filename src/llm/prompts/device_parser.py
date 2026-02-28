"""Prompt for parsing car/vehicle info from user messages."""

DEVICE_PARSE_PROMPT = """Ты — парсер данных для системы записи в автосервис.
Извлеки информацию об автомобиле из сообщения пользователя.

Сообщение: "{user_message}"

Верни JSON и ТОЛЬКО JSON, без markdown, без объяснений:
{{
  "device_category": "car",
  "device_brand": "марка автомобиля или null",
  "device_model": "модель автомобиля (можно с годом) или null",
  "confidence": "high|medium|low"
}}

Правила:
- "тойота", "toyota", "тойоты" → brand: "Toyota"
- "бмв", "bmw", "бэха" → brand: "BMW"
- "мерс", "mercedes", "мерседес", "benz" → brand: "Mercedes"
- "хёндай", "hyundai", "хундай" → brand: "Hyundai"
- "киа", "kia" → brand: "Kia"
- "фольксваген", "volkswagen", "vw" → brand: "Volkswagen"
- "лада", "лада веста", "ваз", "жигули", "нива" → brand: "Lada"
- "форд", "ford" → brand: "Ford"
- "рено", "renault" → brand: "Renault"
- "ниссан", "nissan" → brand: "Nissan"
- "митсубиши", "mitsubishi", "митцубиши" → brand: "Mitsubishi"
- "хонда", "honda" → brand: "Honda"
- "мазда", "mazda" → brand: "Mazda"
- "субару", "subaru" → brand: "Subaru"
- Нормализуй модель: "камри", "camry" → "Camry"; "солярис" → "Solaris"; "вест"/"веста" → "Vesta"
- Если модель неясна, но марка есть → device_model: null, confidence: "medium"
- Если вообще неясно → все null, confidence: "low"

Примеры:
- "тойота камри 2018" → {{"device_category": "car", "device_brand": "Toyota", "device_model": "Camry 2018", "confidence": "high"}}
- "бмв х5" → {{"device_category": "car", "device_brand": "BMW", "device_model": "X5", "confidence": "high"}}
- "лада веста" → {{"device_category": "car", "device_brand": "Lada", "device_model": "Vesta", "confidence": "high"}}
- "машина" → {{"device_category": "car", "device_brand": null, "device_model": null, "confidence": "low"}}"""
