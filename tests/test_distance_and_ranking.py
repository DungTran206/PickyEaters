# -*- coding: utf-8 -*-
"""
#6 Distance: district-level geocoding that never guesses, and distances that carry their basis.
#9 Ranking: soft priorities applied in the order the user stated them.
"""

import pytest

from agent.agent import FoodAgent
from agent.planner import location_clarification
from database.db import reset_database
from database.models import Dish, PricingCalculation, RecommendationCandidate, Restaurant
from services.recommendation import (
    distance_text,
    format_recommendations_output,
    rank_candidates,
    score_candidate,
)
from services.search import SAME_DISTRICT_KM, estimate_distance, resolve_district, search_restaurants


# ---------------------------------------------------------------------------
# #6 Geocoding / distance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("address, district", [
    ("12 Đường 3/2, Quận 10, TP.HCM", "quan 10"),        # "quan 1" must not match "quan 10"
    ("45 Hai Bà Trưng, Quận 1, TP.HCM", "quan 1"),       # street named like a Hà Nội district
    ("105 Nguyễn Tuân, Thanh Xuân, Hà Nội", "thanh xuan"),
    ("Cầu Giấy", "cau giay"),
    ("Số 5 Kim Mã, Hà Nội", None),                       # city only: no guessed district
    ("somewhere", None),
    ("", None),
])
def test_resolve_district(address, district):
    assert resolve_district(address) == district


def test_estimate_distance_reports_its_basis():
    km, basis = estimate_distance("Cầu Giấy, Hà Nội", "Thanh Xuân, Hà Nội")
    assert basis == "district_centroid" and km > 2
    assert estimate_distance("Thanh Xuân", "12 Nguyễn Trãi, Thanh Xuân, Hà Nội") == (SAME_DISTRICT_KM, "same_district")
    assert estimate_distance("Kim Mã, Hà Nội", "Thanh Xuân, Hà Nội") == (None, "unknown")


def test_radius_search_excludes_restaurants_with_unknown_distance():
    assert search_restaurants(user_address="Kim Mã, Hà Nội", radius_km=10.0) == []
    within = search_restaurants(user_address="Thanh Xuân, Hà Nội", radius_km=5.0)
    assert within and all(r.distance_basis in ("same_district", "district_centroid") for r in within)
    assert all(r.distance_km <= 5.0 for r in within)


def _rest(basis: str, km: float = 1.5) -> Restaurant:
    return Restaurant(id="r1", name="Quán", cuisine="Vietnamese", rating=4.5,
                      distance_km=km, delivery_fee=15000, distance_basis=basis)


@pytest.mark.parametrize("basis, expected", [
    ("same_district", "cùng quận"),
    ("district_centroid", "ước tính theo quận"),
    ("unknown", "chưa rõ khoảng cách"),
])
def test_distance_text_labels_estimates(basis, expected):
    assert expected in distance_text(_rest(basis))


def test_unknown_distance_scores_neutral():
    pricing = PricingCalculation(original_price=40000, discount=0, delivery_fee=15000, final_price=55000)
    dish = Dish(id="d1", restaurant_id="r1", name="Phở", price=40000)
    assert score_candidate(dish, _rest("unknown", km=0.1), pricing)["distance_score"] == 0.0


def test_planner_asks_for_district_instead_of_guessing():
    assert location_clarification("Thanh Xuân, Hà Nội") is None
    question = location_clarification("Số 5 Kim Mã, Hà Nội")
    assert question and "quận" in question


def test_agent_asks_for_district_when_address_is_unlocatable():
    reset_database()
    result = FoodAgent(user_id="user_01", force_mock=True).run("muốn ăn phở", user_address="Số 5 Kim Mã, Hà Nội")
    assert result["candidates"] == []
    assert "quận" in result["response"]
    assert not [c for c in result["tool_calls"] if c["tool"] == "recommend_dishes_with_radius"]


def test_card_shows_distance_basis():
    dish = Dish(id="d1", restaurant_id="r1", name="Phở", price=40000)
    pricing = PricingCalculation(original_price=40000, discount=0, delivery_fee=15000, final_price=55000)
    c = RecommendationCandidate(dish=dish, restaurant=_rest("district_centroid", 5.2), pricing=pricing, items=[dish])
    assert "~5.2km (ước tính theo quận)" in format_recommendations_output([c])


# ---------------------------------------------------------------------------
# #9 Ranking by the user's stated priority order
# ---------------------------------------------------------------------------

def _options():
    """Three dishes: A cheap/far, B cheap/near, C pricey/nearest with the best rating."""
    rests = [
        Restaurant(id="rA", name="A", cuisine="Vietnamese", rating=4.2, distance_km=6.0, delivery_fee=15000),
        Restaurant(id="rB", name="B", cuisine="Vietnamese", rating=4.4, distance_km=2.0, delivery_fee=15000),
        Restaurant(id="rC", name="C", cuisine="Vietnamese", rating=4.9, distance_km=0.5, delivery_fee=15000),
    ]
    dishes = [
        Dish(id="A", restaurant_id="rA", name="Phở", price=36000),   # final 51k
        Dish(id="B", restaurant_id="rB", name="Phở", price=38000),   # final 53k (same 10k bucket as A)
        Dish(id="C", restaurant_id="rC", name="Phở", price=70000),   # final 85k
    ]
    return dishes, rests


def _order(priorities):
    dishes, rests = _options()
    task = {"soft_preferences": {"priority_order": priorities}}
    return [c.dish.id for c in rank_candidates(dishes, task_model=task, restaurants=rests, top_k=None)]


def test_price_then_distance():
    # A and B cost practically the same, so distance decides: B (2km) before A (6km).
    assert _order(["price", "distance"]) == ["B", "A", "C"]


def test_distance_then_price():
    assert _order(["distance", "price"]) == ["C", "B", "A"]


def test_rating_first_even_when_price_also_listed():
    assert _order(["rating", "price"])[0] == "C"


def test_first_stated_priority_wins_over_fixed_precedence():
    # Previously "rating" always beat "price" regardless of the order the user gave.
    assert _order(["price", "rating"])[-1] == "C"


def test_unknown_rating_ranks_last_for_rating_priority():
    dishes, rests = _options()
    rests[2] = rests[2].model_copy(update={"rating": None})
    task = {"soft_preferences": {"priority_order": ["rating"]}}
    ranked = rank_candidates(dishes, task_model=task, restaurants=rests, top_k=None)
    assert ranked[-1].dish.id == "C"


def test_price_score_uses_stated_budget_over_profile_budget():
    from database.models import UserPreference
    rest = _rest("stored")
    pref = UserPreference(user_id="u", budget=200000)
    dish = Dish(id="d1", restaurant_id="r1", name="Phở", price=60000)
    pricing = PricingCalculation(original_price=60000, discount=0, delivery_fee=15000, final_price=75000)
    within_profile = score_candidate(dish, rest, pricing, pref, task_model={"objects": []})["price_match"]
    over_stated = score_candidate(dish, rest, pricing, pref,
                                  task_model={"hard_constraints": {"price_max": 50000}})["price_match"]
    assert within_profile > 0 > over_stated
