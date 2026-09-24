# -*- coding: utf-8 -*-
"""
Tests for the VALIDATE layer (agent/validator.py).

Architecture Rules (AGENTS.md):
- VALIDATE owns hard-constraint checking.
- Hard constraints must not be silently relaxed.
- Replanning may change search strategy or soft preferences, but must not violate hard exclusions/constraints.
"""

import pytest
from database.models import Dish, Restaurant, UserPreference, RecommendationCandidate, PricingCalculation
from agent.task_model import TaskModel, TaskObject, HardConstraints
from agent.validator import (
    validate_candidate,
    validate_candidates_list,
    ConstraintViolation,
    ValidationResult
)


def _make_candidate(
    name: str = "Phở bò",
    price: int = 50000,
    delivery_fee: int = 15000,
    spicy: bool = False,
    ingredients = None,
    category: str = "Main"
) -> RecommendationCandidate:
    dish = Dish(
        id="d1",
        restaurant_id="r1",
        name=name,
        price=price,
        spicy=spicy,
        cuisine="Vietnamese",
        category=category,
        ingredients=ingredients or ["beef", "noodles"],
        description=f"Món ngon {name}"
    )
    rest = Restaurant(
        id="r1",
        name="Quán Phở",
        cuisine="Vietnamese",
        rating=4.8,
        distance_km=1.5,
        delivery_fee=delivery_fee,
        platform="ShopeeFood"
    )
    pricing = PricingCalculation(
        original_price=price,
        discount=0,
        delivery_fee=delivery_fee,
        final_price=price + delivery_fee,
        savings=0
    )
    return RecommendationCandidate(
        dish=dish,
        restaurant=rest,
        pricing=pricing,
        items=[dish]
    )


class TestValidateCandidate:
    def test_passes_valid_candidate(self):
        c = _make_candidate("Phở bò", price=50000, delivery_fee=15000)
        task = TaskModel(
            intent="request_recommendation",
            hard_constraints=HardConstraints(price_max=80000, spicy=False),
        )
        res = validate_candidate(c, task)
        assert res.is_valid is True
        assert len(res.violations) == 0

    def test_detects_price_max_violation(self):
        c = _make_candidate("Phở thố đá đặc biệt", price=120000, delivery_fee=15000)
        task = TaskModel(
            intent="request_recommendation",
            hard_constraints=HardConstraints(price_max=80000),
        )
        res = validate_candidate(c, task)
        assert res.is_valid is False
        assert len(res.violations) == 1
        assert res.violations[0].constraint_type == "price_max"
        assert res.violations[0].actual_value == 135000

    def test_detects_spicy_conflict_when_user_requested_non_spicy(self):
        c = _make_candidate("Mì cay cấp độ 3", price=50000, spicy=True)
        task = TaskModel(
            intent="request_recommendation",
            hard_constraints=HardConstraints(spicy=False),
        )
        res = validate_candidate(c, task)
        assert res.is_valid is False
        assert len(res.violations) == 1
        assert res.violations[0].constraint_type == "spicy"
        assert res.violations[0].actual_value is True
        assert res.violations[0].expected_value is False

    def test_detects_spicy_conflict_when_user_requested_spicy(self):
        c = _make_candidate("Cháo gà thanh đạm", price=40000, spicy=False)
        task = TaskModel(
            intent="request_recommendation",
            hard_constraints=HardConstraints(spicy=True),
        )
        res = validate_candidate(c, task)
        assert res.is_valid is False
        assert any(v.constraint_type == "spicy" for v in res.violations)

    def test_detects_ingredient_excludes_from_task_and_profile(self):
        c = _make_candidate("Bún đậu mắm tôm", ingredients=["tofu", "mam tom", "herbs"])
        task = TaskModel(
            intent="request_recommendation",
            ingredient_excludes=["mam tom"],
        )
        res = validate_candidate(c, task)
        assert res.is_valid is False
        assert len(res.violations) == 1
        assert res.violations[0].constraint_type == "ingredient_exclude"

    def test_detects_excluded_concept(self):
        c = _make_candidate("Xôi chim bồ câu", price=55000)
        task = TaskModel(
            intent="request_recommendation",
            excluded_concepts=["xôi"],
        )
        res = validate_candidate(c, task)
        assert res.is_valid is False
        assert len(res.violations) == 1
        assert res.violations[0].constraint_type == "excluded_concept"

    def test_validate_candidates_list_separates_valid_and_rejected_with_evidence(self):
        c_valid = _make_candidate("Phở bò", price=50000)
        c_too_expensive = _make_candidate("Súp vi cá", price=200000)
        c_disliked = _make_candidate("Bún chả", ingredients=["onion", "pork"])

        task = TaskModel(
            intent="request_recommendation",
            hard_constraints=HardConstraints(price_max=100000),
            ingredient_excludes=["onion"]
        )

        valid, rejected = validate_candidates_list([c_valid, c_too_expensive, c_disliked], task)
        assert len(valid) == 1
        assert valid[0].dish.name == "Phở bò"

        assert len(rejected) == 2
        # Verify structured evidence exists for rejected items
        rejected_names = [cand.dish.name for cand, violations in rejected]
        assert "Súp vi cá" in rejected_names
        assert "Bún chả" in rejected_names

        for cand, violations in rejected:
            if cand.dish.name == "Súp vi cá":
                assert any(v.constraint_type == "price_max" for v in violations)
            if cand.dish.name == "Bún chả":
                assert any(v.constraint_type == "ingredient_exclude" for v in violations)
