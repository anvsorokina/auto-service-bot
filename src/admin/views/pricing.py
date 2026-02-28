"""Pricing views — CRUD for price rules."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.admin.dependencies import get_current_shop
from src.database import get_db
from src.models.device import DeviceCategory, RepairType
from src.models.pricing import PriceRule
from src.models.shop import Shop

logger = structlog.get_logger()

router = APIRouter(prefix="/admin/pricing", tags=["admin-pricing"])

import pathlib

TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("", response_class=HTMLResponse)
async def pricing_list(
    request: Request,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """List all price rules for the shop."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    # Fetch price rules with repair types
    result = await db.execute(
        select(PriceRule)
        .where(PriceRule.shop_id == shop.id, PriceRule.is_active == True)  # noqa: E712
        .order_by(PriceRule.priority.desc(), PriceRule.device_brand, PriceRule.device_model_pattern)
    )
    rules = result.scalars().all()

    # Fetch repair types for labels
    rt_result = await db.execute(select(RepairType))
    repair_types = {str(rt.id): rt for rt in rt_result.scalars().all()}

    return templates.TemplateResponse("pricing/list.html", {
        "request": request,
        "shop": shop,
        "active_page": "pricing",
        "rules": rules,
        "repair_types": repair_types,
    })


@router.get("/new", response_class=HTMLResponse)
async def pricing_new(
    request: Request,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Form to create a new price rule."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    # Fetch repair types for select
    rt_result = await db.execute(
        select(RepairType).order_by(RepairType.name_ru)
    )
    repair_types = rt_result.scalars().all()

    return templates.TemplateResponse("pricing/form.html", {
        "request": request,
        "shop": shop,
        "active_page": "pricing",
        "repair_types": repair_types,
        "rule": None,
        "form_action": "/admin/pricing",
        "form_title": "Добавить цену",
    })


@router.post("", response_class=HTMLResponse)
async def pricing_create(
    request: Request,
    repair_type_id: str = Form(...),
    device_brand: str = Form(""),
    device_model_pattern: str = Form(""),
    price_min: float = Form(...),
    price_max: float = Form(...),
    tier: str = Form("standard"),
    tier_description: str = Form(""),
    warranty_months: int = Form(3),
    notes: str = Form(""),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Create a new price rule."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    # Determine priority
    priority = 0
    if device_brand:
        priority = 5
    if device_brand and device_model_pattern:
        priority = 10

    rule = PriceRule(
        shop_id=shop.id,
        repair_type_id=uuid.UUID(repair_type_id) if repair_type_id else None,
        device_brand=device_brand.strip() or None,
        device_model_pattern=device_model_pattern.strip() or None,
        price_min=price_min,
        price_max=price_max,
        tier=tier or "standard",
        tier_description=tier_description.strip() or None,
        warranty_months=warranty_months,
        notes=notes.strip() or None,
        priority=priority,
        is_active=True,
    )
    db.add(rule)
    await db.commit()

    logger.info("price_rule_created", shop_id=str(shop.id), rule_id=str(rule.id))
    return RedirectResponse(url="/admin/pricing", status_code=303)


@router.get("/{rule_id}/edit", response_class=HTMLResponse)
async def pricing_edit(
    request: Request,
    rule_id: str,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Form to edit an existing price rule."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    result = await db.execute(
        select(PriceRule).where(
            PriceRule.id == uuid.UUID(rule_id),
            PriceRule.shop_id == shop.id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return RedirectResponse(url="/admin/pricing")

    rt_result = await db.execute(select(RepairType).order_by(RepairType.name_ru))
    repair_types = rt_result.scalars().all()

    return templates.TemplateResponse("pricing/form.html", {
        "request": request,
        "shop": shop,
        "active_page": "pricing",
        "repair_types": repair_types,
        "rule": rule,
        "form_action": f"/admin/pricing/{rule_id}",
        "form_title": "Редактировать цену",
    })


@router.post("/{rule_id}", response_class=HTMLResponse)
async def pricing_update(
    request: Request,
    rule_id: str,
    repair_type_id: str = Form(...),
    device_brand: str = Form(""),
    device_model_pattern: str = Form(""),
    price_min: float = Form(...),
    price_max: float = Form(...),
    tier: str = Form("standard"),
    tier_description: str = Form(""),
    warranty_months: int = Form(3),
    notes: str = Form(""),
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Update a price rule."""
    if shop is None:
        return RedirectResponse(url="/admin/login")

    priority = 0
    if device_brand.strip():
        priority = 5
    if device_brand.strip() and device_model_pattern.strip():
        priority = 10

    await db.execute(
        update(PriceRule)
        .where(PriceRule.id == uuid.UUID(rule_id), PriceRule.shop_id == shop.id)
        .values(
            repair_type_id=uuid.UUID(repair_type_id) if repair_type_id else None,
            device_brand=device_brand.strip() or None,
            device_model_pattern=device_model_pattern.strip() or None,
            price_min=price_min,
            price_max=price_max,
            tier=tier or "standard",
            tier_description=tier_description.strip() or None,
            warranty_months=warranty_months,
            notes=notes.strip() or None,
            priority=priority,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    logger.info("price_rule_updated", rule_id=rule_id)
    return RedirectResponse(url="/admin/pricing", status_code=303)


@router.delete("/{rule_id}", response_class=HTMLResponse)
async def pricing_delete(
    request: Request,
    rule_id: str,
    shop: Optional[Shop] = Depends(get_current_shop),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a price rule (set is_active=False)."""
    if shop is None:
        return HTMLResponse("Unauthorized", status_code=401)

    await db.execute(
        update(PriceRule)
        .where(PriceRule.id == uuid.UUID(rule_id), PriceRule.shop_id == shop.id)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    await db.commit()

    logger.info("price_rule_deleted", rule_id=rule_id)

    # Return empty for HTMX (row removed)
    return HTMLResponse("")
