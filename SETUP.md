# Repair Bot — Пошаговая настройка

## 1. Supabase (PostgreSQL)

1. Зайди на https://supabase.com → **New Project**
2. Настройки:
   - **Name:** `repair-bot`
   - **Database Password:** запомни или сгенерируй (понадобится!)
   - **Region:** `eu-central-1` (Frankfurt) — ближе к России
3. Подожди 1-2 минуты пока создастся
4. Иди в **Settings → Database → Connection string → URI**
5. Скопируй строку подключения, она будет вида:
   ```
   postgresql://postgres.[project-ref]:[password]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
   ```
6. Замени `postgresql://` на `postgresql+asyncpg://` — это нужно для asyncpg
7. Иди в **SQL Editor** → вставь содержимое файла `scripts/setup_supabase.sql` → **Run**

## 2. Upstash (Redis)

1. Зайди на https://upstash.com → **Create Database**
2. Настройки:
   - **Name:** `repair-bot-redis`
   - **Region:** `eu-west-1` (Ireland) — ближе к России
   - **Type:** Regional
3. Скопируй **UPSTASH_REDIS_REST_URL** в формате:
   ```
   rediss://default:[password]@[host]:6379
   ```

## 3. Anthropic API Key

1. Зайди на https://console.anthropic.com/settings/keys
2. **Create Key** → скопируй `sk-ant-...`

## 4. Telegram Bot

1. Открой @BotFather в Telegram
2. `/newbot` → введи имя (напр. "ФиксПро Помощник")
3. Введи username (напр. `fixpro_helper_bot`)
4. Скопируй токен бота

## 5. Файл .env

Создай `repair-bot/.env`:
```env
DATABASE_URL=postgresql+asyncpg://postgres.[ref]:[password]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
REDIS_URL=rediss://default:[password]@[host].upstash.io:6379
ANTHROPIC_API_KEY=sk-ant-xxxxx
TELEGRAM_WEBHOOK_BASE_URL=https://your-app.railway.app
TELEGRAM_WEBHOOK_SECRET=any-random-string-here
LOG_LEVEL=INFO
ENVIRONMENT=production
```

## 6. Деплой на Railway

1. Зайди на https://railway.com → **New Project → Deploy from GitHub**
2. Выбери `anvsorokina/startup-for-services`
3. Root Directory: `repair-bot`
4. Добавь все переменные из `.env` в **Variables**
5. Deploy!

## 7. Регистрация первого магазина

После деплоя, вызови API:
```bash
curl -X POST https://your-app.railway.app/api/v1/admin/shops \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "fixpro-moscow",
    "name": "ФиксПро Москва",
    "telegram_bot_token": "YOUR_BOT_TOKEN",
    "owner_telegram_id": YOUR_TELEGRAM_USER_ID,
    "language": "ru",
    "currency": "RUB",
    "address": "ул. Ленина, 42"
  }'
```

Это автоматически зарегистрирует webhook в Telegram.

## 8. Тестирование

Открой своего бота в Telegram и напиши `/start` — бот должен ответить!
