# -*- coding: utf-8 -*-
"""
Tests for the PLAN layer (agent/planner.py).
Verifies:
1. Semantic category mapping when concept is None (e.g. 'đồ nước', 'thanh thanh').
2. Multi-object decomposition (Main + Drink with same_restaurant).
3. Explicit constraints and profile fusion.
4. Non-recommendation intent handling.
"""

import pytest

from agent.planner import plan_recommendation, resolve_semantic_keywords
from agent.task_model import (
    FollowUp,
    HardConstraints,
    Relationship,
    SemanticAttribute,
    SoftPreferences,
    TaskContext,
    TaskModel,
    TaskObject,
)


def _make_task(**overrides) -> TaskModel:
    base = {
        "intent": "request_recommendation",
        "objects": [],
        "hard_constraints": HardConstraints(),
        "ingredient_excludes": [],
        "soft_preferences": SoftPreferences(),
        "excluded_concepts": [],
        "semantic_attributes": [],
        "relationships": [],
        "follow_up": None,
        "context": TaskContext(),
    }
    base.update(overrides)
    return TaskModel(**base)


class TestSemanticCategoryMapping:
    def test_do_nuoc_expands_to_noodle_soup_categories(self):
        task = _make_task(
            objects=[TaskObject(role="Main", concept=None, required=True)],
            semantic_attributes=[SemanticAttribute(text="đồ nước", target="object")],
        )
        plan = plan_recommendation(task, "u1", "Cầu Giấy, Hà Nội")
        assert plan is not None
        assert plan["keyword"] is None
        assert "pho" in plan["semantic_keywords"]
        assert "bun" in plan["semantic_keywords"]
        assert "mien" in plan["semantic_keywords"]
        assert "chao" in plan["semantic_keywords"]

    def test_thanh_dam_expands_to_light_categories(self):
        task = _make_task(
            objects=[TaskObject(role="Main", concept=None, required=True)],
            semantic_attributes=[SemanticAttribute(text="thanh thanh", target="object")],
        )
        plan = plan_recommendation(task, "u1")
        assert plan is not None
        assert any(k in plan["semantic_keywords"] for k in ["pho ga", "bun moc", "mien ga", "salad"])

    def test_specific_food_concept_does_not_expand_semantic_keywords(self):
        task = _make_task(
            objects=[TaskObject(role="Main", concept="phở bò", required=True)],
            semantic_attributes=[SemanticAttribute(text="đồ nước", target="object")],
        )
        plan = plan_recommendation(task, "u1")
        assert plan is not None
        assert plan["keyword"] == "phở bò"
        assert plan["semantic_keywords"] == []


class TestMultiObjectDecomposition:
    def test_main_plus_drink_same_restaurant(self):
        task = _make_task(
            objects=[
                TaskObject(role="Main", concept="phở bò", required=True),
                TaskObject(role="Drink", concept="trà chanh", required=True),
            ],
            relationships=[Relationship(type="same_restaurant", objects=[0, 1])],
        )
        plan = plan_recommendation(task, "u1")
        assert plan is not None
        assert plan["keyword"] == "phở bò"
        assert plan["composition_mode"] == "same_restaurant"

    def test_main_plus_drink_without_relationship_is_one_order_not_forced_same_restaurant(self):
        """Several objects are one meal (not independent searches), but "same restaurant"
        is only required when the user said so; it is never inferred from a drink."""
        task = _make_task(
            objects=[
                TaskObject(role="Main", concept="cơm sườn", required=True),
                TaskObject(role="Drink", concept="trà đá", required=False),
            ],
        )
        plan = plan_recommendation(task, "u1")
        assert plan is not None
        assert plan["keyword"] == "cơm sườn"
        assert plan["composition_mode"] == "same_order"


class TestProfileFusionAndConstraints:
    def test_fuses_profile_address_cuisine_and_dislikes(self):
        task = _make_task(
            objects=[TaskObject(role="Main", concept="bún chả", required=True)],
            ingredient_excludes=["hành"],
            hard_constraints=HardConstraints(price_max=50000, spicy=False),
        )
        profile = {
            "address": "Thanh Xuân, Hà Nội",
            "preferred_cuisines": ["Vietnamese"],
            "disliked_ingredients": ["mắm tôm"],
            "preferred_distance": 3.0,
        }
        plan = plan_recommendation(task, "u1", profile=profile)
        assert plan is not None
        assert plan["user_address"] == "Thanh Xuân, Hà Nội"
        assert plan["cuisine"] == "Vietnamese"
        assert set(plan["disliked_ingredients"]) == {"mắm tôm", "hành"}
        assert plan["max_price"] == 50000
        assert plan["spicy"] is False
        assert plan["initial_radius"] == 3.0

    def test_non_recommendation_intent_returns_none(self):
        task = _make_task(intent="state_preference")
        assert plan_recommendation(task, "u1") is None
        task_chit = _make_task(intent="chit_chat")
        assert plan_recommendation(task_chit, "u1") is None
