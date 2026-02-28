"""FastAPI application entry point."""

import logging
import pathlib
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.v1.admin import router as admin_router
from src.api.v1.leads import router as leads_router
from src.api.webhooks.telegram import router as telegram_router
from src.api.webhooks.whatsapp import router as whatsapp_router
from src.admin.router import router as admin_panel_router
from src.admin.views.leads import router as admin_leads_router
from src.admin.views.pricing import router as admin_pricing_router
from src.admin.views.settings import router as admin_settings_router
from src.admin.views.schedule import router as admin_schedule_router
from src.admin.views.dashboard import router as admin_dashboard_router
from src.admin.views.conversations import router as admin_conversations_router
from src.admin.views.chat import router as admin_chat_router
from src.config import settings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer() if settings.environment == "development"
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    ),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info(
        "app_starting",
        environment=settings.environment,
        webhook_base=settings.telegram_webhook_base_url,
    )
    yield
    logger.info("app_shutting_down")


app = FastAPI(
    title="AutoService Bot API",
    description="AI-powered intake bot for independent auto repair shops",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount admin static files
_admin_static = pathlib.Path(__file__).parent / "admin" / "static"
app.mount("/admin/static", StaticFiles(directory=str(_admin_static)), name="admin-static")

# Include routers
app.include_router(telegram_router)
app.include_router(whatsapp_router)
app.include_router(leads_router)
app.include_router(admin_router)
app.include_router(admin_panel_router)
app.include_router(admin_leads_router)
app.include_router(admin_pricing_router)
app.include_router(admin_settings_router)
app.include_router(admin_schedule_router)
app.include_router(admin_dashboard_router)
app.include_router(admin_conversations_router)
app.include_router(admin_chat_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "AutoService Bot API",
        "version": "0.1.0",
        "status": "running",
    }
