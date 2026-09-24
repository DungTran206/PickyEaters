# -*- coding: utf-8 -*-
"""
Tests for the RANK & RESPOND layer (services/recommendation.py).
Verifies:
1. Semantic scoring: boosts dishes matching qualitative attributes (đồ nước, thanh thanh, ăn no, cay nhẹ).
2. Transparent reasoning: generates explanatory bullet points reflecting the user's semantic intent.
3. Ranking order: semantically aligned dishes are promoted to Top 1.
"""

import pytest

from database.models import Dish, PricingCalculation, Restaurant, UserPreference
from services.recommendation import (
    evaluate_semantic_match,
    generate_detailed_reasoning,
    rank_candidates,
    score_candidate,
)


def _make_dish(id: str, name: str, price: int = 50000, desc: str = "", spicy: bool = False, cui: str = "Vietnamese") -> Dish:
    return Dish(
        id=id,
        restaurant_id=f"rest_{id}",
        name=name,
        price=price,
        spicy=spicy,
        cuisine=cui,
        category="Main",
        ingredients=[],
        description=desc,
    )


def _make_restaurant(id: str, rating: float = 4.6, dist: float = 2.0) -> Restaurant:
    return Restaurant(
        id=f"rest_{id}",
        name=f"Quán Ngon {id}",
        cuisine="Vietnamese",
        rating=rating,
        distance_km=dist,
        delivery_fee=15000,
        platform="ShopeeFood",
    )


def _make_pricing(price: int = 50000) -> PricingCalculation:
    return PricingCalculation(
        original_price=price,
        discount=0,
        delivery_fee=15000,
        final_price=price + 15000,
        savings=0,
    )


class TestSemanticEvaluation:
    def test_do_nuoc_scores_soup_and_penalizes_dry(self):
        rest = _make_restaurant("1")
        soup_dish = _make_dish("1", "Phở bò tái lăn", desc="Nước dùng thanh ngọt đậm đà")
        dry_dish = _make_dish("2", "Cơm tấm sườn nướng mỡ hành", desc="Cơm tấm dẻo thơm sườn nướng đậm vị")

        soup_score, soup_reasons = evaluate_semantic_match(soup_dish, rest, [{"text": "đồ nước"}])
        dry_score, _ = evaluate_semantic_match(dry_dish, rest, [{"text": "đồ nước"}])

        assert soup_score > 0
        assert any("món nước" in r for r in soup_reasons)
        assert dry_score < 0

    def test_thanh_thanh_boosts_light_dishes(self):
        rest = _make_restaurant("1")
        light_dish = _make_dish("1", "Cháo sườn sụn", desc="Cháo ninh nhừ thanh đạm nhẹ bụng")
        heavy_dish = _make_dish("2", "Xôi thịt kho trứng mỡ hành", desc="Xôi nếp dẻo thịt kho đậm béo ngậy")

        light_score, light_reasons = evaluate_semantic_match(light_dish, rest, [{"text": "thanh thanh"}])
        heavy_score, _ = evaluate_semantic_match(heavy_dish, rest, [{"text": "thanh thanh"}])

        assert light_score > 0
        assert any("thanh đạm" in r for r in light_reasons)
        assert heavy_score < 0

    def test_cay_nhe_boosts_mild_spicy(self):
        rest = _make_restaurant("1")
        spicy_dish = _make_dish("1", "Mì trộn sốt cay nhẹ", spicy=True, desc="Sốt cay nhẹ thơm nồng")
        score, reasons = evaluate_semantic_match(spicy_dish, rest, [{"text": "cay nhẹ"}])

        assert score > 0
        assert any("cay vừa phải" in r for r in reasons)


class TestReasoningAndRanking:
    def test_detailed_reasoning_includes_semantic_bullet_point(self):
        dish = _make_dish("1", "Phở gà xé lá chanh", desc="Nước dùng thanh ngọt")
        rest = _make_restaurant("1", rating=4.8, dist=1.5)
        pricing = _make_pricing(45000)
        task_model = {
            "objects": [],
            "hard_constraints": {},
            "semantic_attributes": [{"text": "thanh thanh"}],
        }

        reasoning = generate_detailed_reasoning(
            dish=dish,
            restaurant=rest,
            pricing=pricing,
            task_model=task_model,
        )

        assert "Chuẩn vị thanh đạm" in reasoning
        assert "Cách bạn chỉ 1.5km" in reasoning

    def test_semantic_match_promotes_dish_to_top1(self):
        # Two dishes with equal rating & price, but one matches "đồ nước"
        dish_soup = _make_dish("1", "Bún bò Huế giò heo", desc="Nước dùng cay nhẹ đậm đà")
        dish_rice = _make_dish("2", "Cơm sườn nướng", desc="Cơm dẻo sườn nướng")
        rest1 = _make_restaurant("1", rating=4.6, dist=2.0)
        rest2 = _make_restaurant("2", rating=4.6, dist=2.0)

        user_pref = UserPreference(user_id="u1", budget=100000)
        task_model = {
            "objects": [],
            "hard_constraints": {},
            "semantic_attributes": [{"text": "đồ nước"}],
        }

        candidates = rank_candidates(
            dishes=[dish_rice, dish_soup],
            user_pref=user_pref,
            task_model=task_model,
            top_k=2,
            restaurants=[rest1, rest2],
        )

        assert len(candidates) == 2
        # The soup dish should rank #1 because of semantic bonus
        assert candidates[0].dish.id == dish_soup.id
        assert candidates[0].scores.get("semantic_score", 0) > candidates[1].scores.get("semantic_score", 0)
