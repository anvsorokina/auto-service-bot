"""Tests for pricing engine rule matching logic."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from decimal import Decimal

from src.pricing.engine import PricingEngine


class TestPricingRuleMatching:
    """Test the rule matching logic (without DB)."""

    def _make_rule(
        self,
        priority: int = 0,
        device_brand: str | None = None,
        device_model_pattern: str | None = None,
        price_min: float = 1000,
        price_max: float = 5000,
        tier: str = "standard",
    ):
        """Create a mock price rule."""
        rule = MagicMock()
        rule.priority = priority
        rule.device_brand = device_brand
        rule.device_model_pattern = device_model_pattern
        rule.price_min = Decimal(str(price_min))
        rule.price_max = Decimal(str(price_max))
        rule.tier = tier
        rule.tier_description = f"{tier} repair"
        rule.warranty_months = 3
        rule.notes = None
        return rule

    def test_match_generic_rule(self):
        """Generic rule (no brand/model filter) should match anything."""
        engine = PricingEngine()
        rules = [self._make_rule(priority=0)]

        matched = engine._match_rules(rules, "screen_replacement", "Apple", "iPhone 15")
        assert len(matched) == 1

    def test_match_brand_specific(self):
        """Brand-specific rule should only match that brand."""
        engine = PricingEngine()
        rules = [
            self._make_rule(priority=5, device_brand="Apple", price_min=8000),
            self._make_rule(priority=0, price_min=3000),  # generic
        ]

        matched = engine._match_rules(rules, "screen_replacement", "Apple", "iPhone 15")
        assert len(matched) == 2
        assert matched[0].priority == 5  # brand-specific first

    def test_no_match_wrong_brand(self):
        """Brand-specific rule should not match different brand."""
        engine = PricingEngine()
        rules = [
            self._make_rule(priority=5, device_brand="Apple"),
        ]

        matched = engine._match_rules(rules, "screen_replacement", "Samsung", "Galaxy S24")
        assert len(matched) == 0

    def test_match_model_pattern(self):
        """Model pattern with wildcard should match."""
        engine = PricingEngine()
        rules = [
            self._make_rule(
                priority=10,
                device_brand="Apple",
                device_model_pattern="iphone 15%",
                price_min=10000,
            ),
        ]

        matched = engine._match_rules(
            rules, "screen_replacement", "Apple", "iPhone 15 Pro"
        )
        assert len(matched) == 1
        assert matched[0].priority == 10

    def test_priority_sorting(self):
        """Rules should be sorted by priority, highest first."""
        engine = PricingEngine()
        rules = [
            self._make_rule(priority=0, price_min=3000),
            self._make_rule(priority=10, device_brand="Apple", device_model_pattern="iphone 15%", price_min=10000),
            self._make_rule(priority=5, device_brand="Apple", price_min=8000),
        ]

        matched = engine._match_rules(
            rules, "screen_replacement", "Apple", "iPhone 15 Pro"
        )
        assert matched[0].priority == 10
        assert matched[1].priority == 5
        assert matched[2].priority == 0

    def test_no_rules(self):
        """Empty rules should return empty matches."""
        engine = PricingEngine()
        matched = engine._match_rules([], "screen_replacement", "Apple", "iPhone 15")
        assert len(matched) == 0
