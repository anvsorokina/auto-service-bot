# CLAUDE.md — Project Instructions for Claude Code

## Project: InGarage Auto-Service Bot
FastAPI backend + Telegram bot + Claude AI conversation engine + landing page.

## Tech Stack
- **Backend:** Python 3.11, FastAPI, uvicorn
- **DB:** PostgreSQL 16 (asyncpg + SQLAlchemy 2.0 + Alembic)
- **Cache:** Redis 7
- **AI:** Anthropic Claude API (anthropic 0.84.0)
- **Channels:** Telegram Bot API, WhatsApp (planned)
- **Deploy:** Railway

## Startup (every session)
Before running the server, start dependencies:
```bash
pg_ctlcluster 16 main start
redis-server --daemonize yes
```
Then start the app:
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```
**Note:** localhost:8000 is NOT accessible from the user's browser — the server runs inside the cloud sandbox. Use `curl` to test endpoints locally.

## Environment Variables
- `.env` is in `.gitignore` — never commit it
- Secrets (tokens, API keys) go in `.env` locally and in Railway dashboard for production
- Key vars: `DATABASE_URL`, `REDIS_URL`, `ANTHROPIC_API_KEY`, `NOTIFY_TG_BOT_TOKEN`, `NOTIFY_TG_CHAT_ID`

## Telegram Notifications
- Bot token and chat_id are configured in `.env`
- Notification module: `src/notifications/telegram.py`

## Installed Agents (~/.claude/agents/)
Use these subagents for specialized tasks:
- **python-pro** — Python code quality, patterns, optimization
- **postgres-pro** — SQL queries, schema design, migrations
- **prompt-engineer** — Claude AI prompt design and optimization
- **api-designer** — REST API endpoint design
- **code-reviewer** — Code review before commits/deploys
- **debugger** — Bug investigation and fixing
- **test-automator** — Writing and running tests
- **deployment-engineer** — Deploy to Railway, CI/CD
- **docker-expert** — Dockerfiles, compose, containerization

## Working Style
- Be autonomous: do everything possible without asking the user
- When user action IS required (e.g., Railway dashboard, browser testing, payments), give **clear step-by-step instructions** in Russian
- Always use installed agents for their specialized domains
- Run `code-reviewer` agent before significant commits
- Write clear commit messages in English
- Communicate with the user in Russian

## Project Structure
```
src/
  main.py              — App entrypoint, lifespan, routers
  config.py            — Settings (pydantic-settings)
  database.py          — SQLAlchemy async engine + session
  redis_client.py      — Redis connection
  models/              — SQLAlchemy models
  schemas/             — Pydantic schemas
  repositories/        — DB access layer
  api/                 — REST API routers
  admin/               — Admin panel
  bot/                 — Telegram bot (handlers, middleware, factory)
  conversation/        — Dialog engine (steps, session, engine)
  llm/                 — Claude AI integration (client, generator, prompts)
  landing/             — Landing page (router, templates)
  notifications/       — Telegram notifications
  pricing/             — Price calculation
  whatsapp/            — WhatsApp integration
```
