# InGarage AI — Context for Claude Code

## Project Overview

**InGarage AI** — SaaS-платформа для автоматизации приёма заказов в независимых автосервисах через AI чат-бота (Telegram/WhatsApp). Бот работает 24/7, распознаёт марки авто (включая русский жаргон), собирает описание проблемы, предоставляет смету и бронирует место в расписании.

- **Repo**: github.com/anvsorokina/auto-service-bot
- **Production URL**: auto-service-bot-production.up.railway.app
- **Deployment**: Railway (deploys from `main` branch)
- **Landing page**: GitHub Pages from `docs/` directory

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy async, asyncpg
- **Database**: PostgreSQL (Supabase), Redis (Upstash)
- **LLM**: Anthropic Claude API
- **Telegram**: aiogram 3.x
- **WhatsApp**: Twilio API
- **Admin Panel**: Jinja2 + HTMX (custom dark theme CSS, no CSS frameworks)
- **Fonts**: Syne (headings) + DM Sans (body)
- **Deployment**: Railway + Docker

## Project Structure

```
src/
├── admin/              # Admin panel (FastAPI + Jinja2)
│   ├── routes.py       # Admin routes
│   ├── static/
│   │   └── style.css   # Main CSS (dark theme, 530+ lines)
│   └── templates/
│       ├── base.html           # Base layout with sidebar
│       ├── login.html          # Telegram login page
│       ├── dashboard.html      # Analytics dashboard
│       ├── conversations/      # Client conversations
│       │   ├── list.html
│       │   ├── detail.html
│       │   └── partials/table.html
│       ├── leads/              # Lead management
│       │   ├── list.html
│       │   ├── detail.html
│       │   └── partials/table.html
│       ├── pricing/            # Pricing rules
│       │   ├── list.html
│       │   └── form.html
│       ├── schedule/           # Calendar
│       │   └── calendar.html
│       ├── settings/           # Shop settings
│       │   └── index.html
│       └── chat/               # Chat panel
│           └── panel.html
├── api/                # REST API endpoints
├── bot/                # Telegram bot handlers
├── conversation/       # ConversationEngine (LLM dialog)
├── llm/                # LLM integration (Claude API)
├── models/             # SQLAlchemy models
├── pricing/            # PricingEngine
├── repositories/       # Data access layer
├── schemas/            # Pydantic schemas
├── whatsapp/           # WhatsApp/Twilio integration
├── notifications/      # Notification system
├── config.py           # Settings (pydantic-settings)
├── database.py         # DB connection
├── redis_client.py     # Redis connection
└── main.py             # FastAPI app entry point
docs/
└── index.html          # Landing page (GitHub Pages)
.github/
└── workflows/
    └── deploy-pages.yml  # GitHub Pages deployment workflow
scripts/                # Setup scripts
tests/                  # pytest tests
```

## Design System (Admin Panel — Dark Theme)

CSS variables defined in `src/admin/static/style.css`:

```css
:root {
    --black: #0a0a0a;
    --white: #f5f3ee;
    --accent: #e8ff47;        /* Lime green — primary accent */
    --accent-hover: #d4eb33;
    --accent2: #ff5c35;       /* Orange-red — secondary accent */
    --gray: #1a1a1a;          /* Card backgrounds */
    --gray2: #2a2a2a;         /* Input backgrounds */
    --gray3: #333;            /* Borders */
    --muted: #888;            /* Muted text */
    --border: rgba(255,255,255,0.08);
    --border-light: rgba(255,255,255,0.12);
    --success: #4ade80;
    --warning: #fbbf24;
    --danger: #f87171;
    --info: #60a5fa;
}
```

- No CSS frameworks (pico.min.css was removed)
- Pill-shaped buttons (border-radius: 100px)
- Google Fonts: Syne (headings, 600-800 weight) + DM Sans (body)
- Dark background throughout, light text

## Git & Deployment Notes

- **Railway deploys from `main` branch** — changes must be merged to `main` for production
- **Claude Code can only push to `claude/*` branches** — use PRs to merge into `main`
- Current feature branch: `claude/recover-session-context-TENzt`

## Key Business Context

- **Target market**: Independent auto repair shops in Russia, Kazakhstan, Uzbekistan (~68K TAM)
- **Language**: Russian-first (UI, bot dialogs, жаргонные названия авто)
- **Multi-tenant**: One deployment serves many shops, each with their own Telegram bot
- **Pricing model**: Free (50 dialogs/month) → Pro ($89/month, 500 dialogs) → Enterprise
- **Authentication**: Telegram Login Widget for admin panel access

## Current TODO (from TODO.md)

1. Персонализация бота под конкретный сервис (специалисты, виды работ)
2. Обучить бота контексту автосервисной тематики (сейчас может предложить нерелевантную услугу)
3. Если клиент отказывается из-за цены — бот должен передавать диалог оператору с уведомлением

## Pending Actions

- PR `claude/recover-session-context-TENzt → main` нужно смержить через GitHub UI для деплоя
- После мержа — включить GitHub Pages в Settings → Pages → Source: GitHub Actions
