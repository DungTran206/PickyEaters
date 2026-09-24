# -*- coding: utf-8 -*-
"""
Tests for the COMPOSE layer (agent/composer.py).

Architecture Rules (AGENTS.md):
- COMPOSE builds multi-object orders.
- Multiple objects are not automatically independent searches.
- Use TaskModel relationships such as same_order or same_restaurant when explicitly represented.
- Budget validation for a composed order happens after composition.
"""

import pytest
from database.models import Dish, Restaurant, UserPreference, Promotion
from agent.task_model import TaskModel, TaskObject, Relationship, HardConstraints
from agent.composer import (
    compose_candidates,
    is_composed_order_request,
    match_dish_to_task_object
)
from services.recommendation import format_recommendations_output


def _make_dish(id: str, rest_id: str, name: str, price: int = 50000, category: str = "Main", ingredients=None, spicy: bool = False) -> Dish:
    return Dish(
        id=id,
        restaurant_id=rest_id,
        name=name,
        price=price,
        spicy=spicy,
        cuisine="Vietnamese",
        category=category,
        ingredients=ingredients or [],
        description=f"Món ngon {name}",
    )


def _make_restaurant(id: str, name: str = "Quán A", rating: float = 4.8, dist: float = 1.8, delivery_fee: int = 15000) -> Restaurant:
    return Restaurant(
        id=id,
        name=name,
        cuisine="Vietnamese",
        rating=rating,
        distance_km=dist,
        delivery_fee=delivery_fee,
        platform="ShopeeFood",
    )


class TestComposeOrder:
    def test_is_composed_order_request(self):
        # 1 object is not composed
        task_single = TaskModel(
            intent="request_recommendation",
            objects=[TaskObject(role="Main", concept="phở bò")],
        )
        assert is_composed_order_request(task_single) is False

        # 2 objects with same_restaurant relationship
        task_multi = TaskModel(
            intent="request_recommendation",
            objects=[
                TaskObject(role="Main", concept="phở bò"),
                TaskObject(role="Side", concept="quẩy"),
            ],
            relationships=[Relationship(type="same_restaurant", objects=[0, 1])],
        )
        assert is_composed_order_request(task_multi) is True

    def test_compose_pairs_main_and_side_from_same_restaurant(self):
        # Rest 1 has both Phở and Quẩy
        rest1 = _make_restaurant("r1", name="Phở Bát Đàn")
        pho1 = _make_dish("d1", "r1", "Phở bò tái lăn", price=55000, category="Main")
        quay1 = _make_dish("d2", "r1", "Quẩy giòn nóng hổi", price=10000, category="Side")

        # Rest 2 has only Cơm, NO quẩy
        rest2 = _make_restaurant("r2", name="Cơm Sườn")
        com2 = _make_dish("d3", "r2", "Cơm tấm sườn", price=50000, category="Main")

        task = TaskModel(
            intent="request_recommendation",
            objects=[
                TaskObject(role="Main", concept="phở bò"),
                TaskObject(role="Side", concept="quẩy"),
            ],
            relationships=[Relationship(type="same_restaurant", objects=[0, 1])],
        )

        candidates = compose_candidates(
            task=task,
            dishes=[pho1, quay1, com2],
            restaurants=[rest1, rest2],
        )

        # Only Rest 1 should produce a combo
        assert len(candidates) == 1
        c = candidates[0]
        assert c.restaurant.id == "r1"
        assert len(c.items) == 2
        assert c.items[0].name == "Phở bò tái lăn"
        assert c.items[1].name == "Quẩy giòn nóng hổi"
        # Subtotal: 55k + 10k = 65k, + 15k ship = 80k final price
        assert c.pricing.original_price == 65000
        assert c.pricing.delivery_fee == 15000
        assert c.pricing.final_price == 80000

    def test_post_composition_budget_validation(self):
        """Rule 8: Budget validation for a composed order happens after composition."""
        rest1 = _make_restaurant("r1", name="Quán Cao Cấp", delivery_fee=15000)
        main1 = _make_dish("d1", "r1", "Bít tết bò", price=90000, category="Main")
        drink1 = _make_dish("d2", "r1", "Trà đào cam sả", price=35000, category="Drink")
        # Combo 1 subtotal: 125k (exceeds budget 100k)

        rest2 = _make_restaurant("r2", name="Quán Bình Dân", delivery_fee=15000)
        main2 = _make_dish("d3", "r2", "Cơm sườn nướng", price=50000, category="Main")
        drink2 = _make_dish("d4", "r2", "Trà tắc mật ong", price=15000, category="Drink")
        # Combo 2 subtotal: 65k (fits within budget 100k)

        task = TaskModel(
            intent="request_recommendation",
            objects=[
                TaskObject(role="Main", concept=None),
                TaskObject(role="Drink", concept=None),
            ],
            hard_constraints=HardConstraints(price_max=100000),
            relationships=[Relationship(type="same_restaurant", objects=[0, 1])],
        )

        candidates = compose_candidates(
            task=task,
            dishes=[main1, drink1, main2, drink2],
            restaurants=[rest1, rest2],
        )

        # Rest 1 must be filtered out post-composition because 125k > 100k
        assert len(candidates) == 1
        assert candidates[0].restaurant.id == "r2"
        assert candidates[0].pricing.original_price == 65000

    def test_single_delivery_fee_applied_for_combo(self):
        """Multiple items from the same restaurant incur only ONE delivery fee."""
        rest = _make_restaurant("r1", delivery_fee=16000)
        dish1 = _make_dish("d1", "r1", "Bún chả", price=45000)
        dish2 = _make_dish("d2", "r1", "Nem cua bể", price=25000, category="Side")

        task = TaskModel(
            intent="request_recommendation",
            objects=[
                TaskObject(role="Main", concept="bún chả"),
                TaskObject(role="Side", concept="nem"),
            ],
            relationships=[Relationship(type="same_restaurant", objects=[0, 1])],
        )

        candidates = compose_candidates(task, dishes=[dish1, dish2], restaurants=[rest])
        assert len(candidates) == 1
        # Delivery fee is 16k, not 32k
        assert candidates[0].pricing.delivery_fee == 16000
        assert candidates[0].pricing.final_price == 45000 + 25000 + 16000

    def test_disliked_ingredients_rejects_combo_if_secondary_contains_it(self):
        rest = _make_restaurant("r1")
        main = _make_dish("d1", "r1", "Phở bò", price=50000, ingredients=["beef", "noodles"])
        # Side contains onion which is disliked
        side = _make_dish("d2", "r1", "Hành trần nước béo", price=10000, category="Side", ingredients=["onion"])

        task = TaskModel(
            intent="request_recommendation",
            objects=[
                TaskObject(role="Main", concept="phở"),
                TaskObject(role="Side", concept="hành"),
            ],
            ingredient_excludes=["onion"],
            relationships=[Relationship(type="same_restaurant", objects=[0, 1])],
        )

        user_pref = UserPreference(user_id="u1", disliked_ingredients=["onion"])
        candidates = compose_candidates(task, dishes=[main, side], restaurants=[rest], user_pref=user_pref)
        # Must be rejected because side has onion
        assert len(candidates) == 0

    def test_format_recommendations_output_for_combo(self):
        rest = _make_restaurant("r1", name="Phở Bát Đàn")
        main = _make_dish("d1", "r1", "Phở bò tái lăn", price=55000)
        side = _make_dish("d2", "r1", "Quẩy giòn phở", price=10000, category="Side")

        task = TaskModel(
            intent="request_recommendation",
            objects=[
                TaskObject(role="Main", concept="phở bò"),
                TaskObject(role="Side", concept="quẩy"),
            ],
            relationships=[Relationship(type="same_restaurant", objects=[0, 1])],
        )

        candidates = compose_candidates(task, dishes=[main, side], restaurants=[rest])
        assert len(candidates) == 1

        output = format_recommendations_output(candidates)
        assert "Combo: Phở bò tái lăn + Quẩy giòn phở" in output
        assert "Chi tiết combo:" in output
        assert "Phở bò tái lăn: 55,000đ" in output
        assert "Quẩy giòn phở: 10,000đ" in output
        assert "Phí ship chung: 15,000đ" in output
