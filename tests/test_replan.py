# -*- coding: utf-8 -*-
"""
Tests for the RE-PLAN layer (agent/replan.py).

Architecture Rules (AGENTS.md):
- RE-PLAN is a bounded strategy loop.
- Do not hard-code one special-case fallback such as only '5 km -> 10 km'.
- Replanning should be driven by structured failure/observation state.
- Hard constraints must not be silently relaxed.
"""

import pytest
from database.models import Dish, Restaurant, RecommendationCandidate, PricingCalculation
from agent.task_model import TaskModel, TaskObject, HardConstraints, Relationship
from agent.validator import ConstraintViolation
from agent.replan import diagnose_and_replan, ReplanAction


def _make_candidate(name: str = "Phở bò", final_price: int = 65000) -> RecommendationCandidate:
    dish = Dish(
        id="d1",
        restaurant_id="r1",
        name=name,
        price=final_price - 15000,
        cuisine="Vietnamese",
        category="Main"
    )
    rest = Restaurant(
        id="r1",
        name="Quán Ngon",
        cuisine="Vietnamese",
        rating=4.7,
        distance_km=2.0,
        delivery_fee=15000,
        platform="ShopeeFood"
    )
    pricing = PricingCalculation(
        original_price=final_price - 15000,
        discount=0,
        delivery_fee=15000,
        final_price=final_price,
        savings=0
    )
    return RecommendationCandidate(
        dish=dish,
        restaurant=rest,
        pricing=pricing,
        items=[dish]
    )


class TestReplanDiagnostics:
    def test_replan_suggests_budget_adjustment_when_all_rejected_by_price_max(self):
        c1 = _make_candidate("Bún bò đặc biệt", final_price=65000)
        c2 = _make_candidate("Bún bò giò heo", final_price=55000)

        rejected = [
            (c1, [ConstraintViolation(constraint_type="price_max", field="price", message="Vượt ngân sách")]),
            (c2, [ConstraintViolation(constraint_type="price_max", field="price", message="Vượt ngân sách")]),
        ]

        task = TaskModel(
            intent="request_recommendation",
            objects=[TaskObject(role="Main", concept="bún bò")],
            hard_constraints=HardConstraints(price_max=40000),
        )

        action = diagnose_and_replan(
            task=task,
            rejected_candidates=rejected,
            current_radius_km=5.0,
            is_radius_expanded=False,
            dishes_retrieved_count=2,
        )

        assert action.strategy == "suggest_budget_adjustment"
        assert action.diagnosis == "budget_too_tight"
        # Minimum available price should be 55k
        assert action.suggested_budget == 55000
        assert "55,000đ" in action.message_to_user
        assert len(action.suggested_alternatives) > 0

    def test_replan_suggests_alternatives_when_all_rejected_by_ingredient_excludes(self):
        c = _make_candidate("Bún đậu mắm tôm", final_price=45000)
        rejected = [
            (c, [ConstraintViolation(constraint_type="ingredient_exclude", field="ingredients", message="Chứa mắm tôm")]),
        ]

        task = TaskModel(
            intent="request_recommendation",
            objects=[TaskObject(role="Main", concept="bún đậu")],
            ingredient_excludes=["mắm tôm"],
        )

        action = diagnose_and_replan(
            task=task,
            rejected_candidates=rejected,
            current_radius_km=5.0,
            is_radius_expanded=False,
            dishes_retrieved_count=1,
        )

        assert action.strategy == "suggest_alternatives"
        assert action.diagnosis == "ingredient_conflict"
        assert "mắm tôm" in action.message_to_user
        # Never silently relaxes the hard exclusion
        assert "Để đảm bảo an toàn" in action.message_to_user

    def test_replan_suggests_radius_expansion_when_no_dishes_in_initial_radius(self):
        task = TaskModel(
            intent="request_recommendation",
            objects=[TaskObject(role="Main", concept="cơm tấm")],
        )

        action = diagnose_and_replan(
            task=task,
            rejected_candidates=[],
            current_radius_km=5.0,
            is_radius_expanded=False,
            dishes_retrieved_count=0,
        )

        assert action.strategy == "expand_radius"
        assert action.diagnosis == "no_restaurants_in_initial_radius"
        assert action.suggested_radius_km == 10.0
        assert "10km" in action.message_to_user

    def test_replan_suggests_combo_substitute_when_pairing_unavailable(self):
        task = TaskModel(
            intent="request_recommendation",
            objects=[
                TaskObject(role="Main", concept="phở bò"),
                TaskObject(role="Drink", concept="sinh tố bơ"),
            ],
            relationships=[Relationship(type="same_restaurant", objects=[0, 1])],
        )

        action = diagnose_and_replan(
            task=task,
            rejected_candidates=[],
            current_radius_km=10.0,
            is_radius_expanded=True,
            dishes_retrieved_count=3,
        )

        assert action.strategy == "suggest_combo_substitute"
        assert action.diagnosis == "combo_pair_not_found"
        assert "phở bò" in action.message_to_user
        assert "sinh tố bơ" in action.message_to_user
