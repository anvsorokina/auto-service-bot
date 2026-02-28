"""Main admin router — login, logout, and mount all view routers."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.admin.auth import (
    create_session,
    delete_session,
    verify_telegram_login,
)
from src.admin.dependencies import get_current_shop
from src.database import get_db
from src.models.shop import Shop
from src.redis_client import get_redis

logger = structlog.get_logger()

router = APIRouter(prefix="/admin", tags=["admin-panel"])

# Templates directory relative to this file
import pathlib

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show Telegram Login Widget page."""
    return templates.TemplateResponse("login.html", {
        "request": request,
    })


@router.post("/auth/telegram")
async def telegram_auth(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Telegram Login Widget callback.

    Telegram sends data as query params or form data.
    We verify the hash and create a session.
    """
    # Get auth data from form or query params
    form = await request.form()
    auth_data = dict(form)

    if not auth_data or "id" not in auth_data:
        # Try query params
        auth_data = dict(request.query_params)

    if not auth_data or "id" not in auth_data:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Не удалось получить данные авторизации",
        })

    telegram_id = int(auth_data["id"])

    # Find shop by owner_telegram_id (use first() to handle multiple shops)
    result = await db.execute(
        select(Shop).where(
            Shop.owner_telegram_id == telegram_id,
            Shop.is_active == True,  # noqa: E712
        ).order_by(Shop.created_at.desc())
    )
    shop = result.scalars().first()

    if not shop:
        logger.warning("admin_login_no_shop", telegram_id=telegram_id)
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Мастерская не найдена. Убедитесь, что ваш Telegram ID привязан к мастерской.",
        })

    # Verify Telegram login hash (skip in dev mode with auth_date=0)
    is_dev_login = str(auth_data.get("auth_date", "")) == "0"
    if shop.telegram_bot_token and not is_dev_login:
        if not verify_telegram_login(auth_data, shop.telegram_bot_token):
            logger.warning("admin_login_invalid_hash", telegram_id=telegram_id)
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Ошибка проверки авторизации. Попробуйте ещё раз.",
            })

    if is_dev_login:
        logger.info("admin_dev_login", telegram_id=telegram_id)

    # Create session
    redis = await get_redis()
    token = await create_session(
        redis=redis,
        shop_id=str(shop.id),
        telegram_id=telegram_id,
        shop_name=shop.name,
    )

    # Set cookie and redirect
    response = RedirectResponse(url="/admin/leads", status_code=303)
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,  # 24 hours
    )

    logger.info("admin_login_success", shop_id=str(shop.id), shop_name=shop.name)
    return response


@router.get("/auth/telegram")
async def telegram_auth_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Telegram Login Widget callback via GET (redirect mode)."""
    # Telegram Login Widget can redirect with query params
    auth_data = dict(request.query_params)

    if not auth_data or "id" not in auth_data:
        return RedirectResponse(url="/admin/login")

    telegram_id = int(auth_data["id"])

    result = await db.execute(
        select(Shop).where(
            Shop.owner_telegram_id == telegram_id,
            Shop.is_active == True,  # noqa: E712
        ).order_by(Shop.created_at.desc())
    )
    shop = result.scalars().first()

    if not shop:
        return RedirectResponse(url="/admin/login?error=shop_not_found")

    is_dev_login = str(auth_data.get("auth_date", "")) == "0"
    if shop.telegram_bot_token and not is_dev_login:
        if not verify_telegram_login(auth_data, shop.telegram_bot_token):
            return RedirectResponse(url="/admin/login?error=invalid_hash")

    redis = await get_redis()
    token = await create_session(
        redis=redis,
        shop_id=str(shop.id),
        telegram_id=telegram_id,
        shop_name=shop.name,
    )

    response = RedirectResponse(url="/admin/leads", status_code=303)
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )
    return response


@router.get("/logout")
async def logout(
    admin_token: Optional[str] = Cookie(None),
):
    """Clear session and redirect to login."""
    if admin_token:
        redis = await get_redis()
        await delete_session(redis, admin_token)

    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("admin_token")
    return response


@router.get("/", response_class=HTMLResponse)
async def admin_root(
    shop: Optional[Shop] = Depends(get_current_shop),
):
    """Redirect to leads or login."""
    if shop is None:
        return RedirectResponse(url="/admin/login")
    return RedirectResponse(url="/admin/leads")
