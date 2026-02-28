"""Pricing Engine — finds matching price rules for a repair request."""

from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.device import RepairType
from src.models.pricing import PriceRule
from src.schemas.lead import PriceEstimate, PriceTier

logger = structlog.get_logger()


class PricingEngine:
    """Finds and applies pricing rules with priority-based matching."""

    async def estimate(
        self,
        db: AsyncSession,
        shop_id: str,
        repair_type_slug: Optional[str],
        device_brand: Optional[str] = None,
        device_model: Optional[str] = None,
    ) -> PriceEstimate:
        """Find matching price rules and return estimate.

        Priority matching:
        1. Exact brand + model + repair type (priority=10)
        2. Brand + repair type only (priority=5)
        3. Repair type only (priority=0) — generic fallback

        Args:
            db: Database session
            shop_id: Shop UUID
            repair_type_slug: Category of repair (e.g., "screen_replacement")
            device_brand: Brand name (e.g., "Apple")
            device_model: Model name (e.g., "iPhone 15 Pro")

        Returns:
            PriceEstimate with tiers and confidence
        """
        if not repair_type_slug:
            return PriceEstimate(
                confidence="none",
                message="Стоимость определяется после диагностики",
            )

        # Resolve repair_type_slug → repair_type_id
        repair_type_id = None
        rt_result = await db.execute(
            select(RepairType.id).where(RepairType.slug == repair_type_slug)
        )
        rt_row = rt_result.scalar_one_or_none()
        if rt_row:
            repair_type_id = rt_row

        # Query active rules for this shop, optionally filtered by repair type
        conditions = [
            PriceRule.shop_id == shop_id,
            PriceRule.is_active == True,  # noqa: E712
        ]
        if repair_type_id:
            # Rules matching this repair type OR generic rules (no repair type)
            conditions.append(
                (PriceRule.repair_type_id == repair_type_id)
                | (PriceRule.repair_type_id.is_(None))
            )

        stmt = (
            select(PriceRule)
            .where(and_(*conditions))
            .order_by(PriceRule.priority.desc())
        )

        result = await db.execute(stmt)
        all_rules = result.scalars().all()

        if not all_rules:
            return PriceEstimate(
                confidence="none",
                message="Стоимость определяется после диагностики",
            )

        # Filter rules matching the repair and device
        matching_rules = self._match_rules(
            all_rules, repair_type_slug, device_brand, device_model
        )

        if not matching_rules:
            return PriceEstimate(
                confidence="low",
                message="Точную стоимость мастер назовёт при осмотре",
            )

        # Group by tier
        tiers = []
        for rule in matching_rules:
            tiers.append(
                PriceTier(
                    tier=rule.tier or "standard",
                    label_ru=rule.tier_description or "Стандартный ремонт",
                    label_en=rule.tier or "Standard repair",
                    price_min=float(rule.price_min),
                    price_max=float(rule.price_max),
                    warranty_months=rule.warranty_months,
                    description=rule.notes,
                )
            )

        # Determine confidence
        best_priority = matching_rules[0].priority
        confidence = "high" if best_priority >= 10 else "medium" if best_priority >= 5 else "low"

        # Overall price range
        price_min = min(float(r.price_min) for r in matching_rules)
        price_max = max(float(r.price_max) for r in matching_rules)

        logger.info(
            "price_estimated",
            shop_id=shop_id,
            repair=repair_type_slug,
            brand=device_brand,
            model=device_model,
            tiers=len(tiers),
            confidence=confidence,
            range=f"{price_min}-{price_max}",
        )

        return PriceEstimate(
            tiers=tiers,
            confidence=confidence,
            duration_minutes=60,
        )

    def _match_rules(
        self,
        rules: list[PriceRule],
        repair_type_slug: str,
        device_brand: Optional[str],
        device_model: Optional[str],
    ) -> list[PriceRule]:
        """Filter rules by matching criteria with priority ordering."""
        matched = []
        for rule in rules:
            # Check brand match
            if rule.device_brand and device_brand:
                if rule.device_brand.lower() != device_brand.lower():
                    continue
            elif rule.device_brand:
                continue  # Rule requires specific brand but we don't have one

            # Check model pattern match
            if rule.device_model_pattern and device_model:
                pattern = rule.device_model_pattern.lower()
                model = device_model.lower()
                # Simple pattern matching (% as wildcard)
                if "%" in pattern:
                    prefix = pattern.replace("%", "")
                    if not model.startswith(prefix):
                        continue
                elif pattern != model:
                    continue
            elif rule.device_model_pattern:
                continue  # Rule requires specific model but we don't have one

            matched.append(rule)

        # Sort by priority (highest first)
        matched.sort(key=lambda r: r.priority, reverse=True)
        return matched
