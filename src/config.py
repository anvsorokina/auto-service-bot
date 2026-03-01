"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str

    # Redis
    redis_url: str

    # Anthropic
    anthropic_api_key: str

    # Telegram
    telegram_webhook_base_url: str
    telegram_webhook_secret: str

    # Twilio (WhatsApp)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""  # e.g. "+14155238886" for sandbox

    # App
    log_level: str = "INFO"
    environment: str = "development"

    # Admin panel — used as API key for /api/v1/admin/* endpoints
    admin_secret_key: str

    # LLM
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 300

    # Landing page — Telegram notifications for demo requests
    landing_tg_bot_token: str = ""
    landing_tg_chat_id: int = 0

    # Session
    session_ttl_seconds: int = 7200  # 2 hours

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()  # type: ignore[call-arg]
