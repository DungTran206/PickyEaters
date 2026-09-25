# -*- coding: utf-8 -*-
"""
Crawled data must not invent facts (AGENTS.md anti-pattern: fake scraper defaults).

- Missing/invalid source values stay unknown or are explicitly marked in
  Restaurant.estimated_fields; RESPOND labels or omits them.
- Records we cannot locate are skipped rather than given a made-up address.
- Promotion text without amount/conditions never becomes a Promotion.
"""

from database.models import Dish, PricingCalculation, RecommendationCandidate, Restaurant
from services.recommendation import (
    format_recommendations_output,
    generate_detailed_reasoning,
    score_candidate,
)
from services.search import (
    ESTIMATED_DELIVERY_FEE,
    _crawled_restaurant,
    load_menus,
    load_promotions,
    load_restaurants,
    search_restaurants,
)


class TestCrawledRestaurant:
    def test_missing_address_is_skipped_not_invented(self):
        assert _crawled_restaurant({"restaurant_name": "Quán A"}, "GrabFood", "gf_1") is None

    def test_unlocatable_address_is_skipped(self):
        assert _crawled_restaurant(
            {"restaurant_name": "Quán A", "address": "Nowhere street"}, "GrabFood", "gf_1"
        ) is None

    def test_missing_values_are_unknown_or_marked_estimated(self):
        r = _crawled_restaurant(
            {"restaurant_name": "Quán A", "address": "1 Lê Đại Hành, Hai Bà Trưng, Hà Nội"},
            "ShopeeFood", "sf_1",
        )
        assert r.rating is None
        assert r.open_hours == ""
        assert r.delivery_fee == ESTIMATED_DELIVERY_FEE
        assert set(r.estimated_fields) == {"delivery_fee", "delivery_time_mins", "cuisine"}
        assert r.district == "Hai Bà Trưng"

    def test_out_of_range_rating_is_dropped(self):
        r = _crawled_restaurant(
            {"restaurant_name": "Quán A", "address": "Cầu Giấy, Hà Nội", "rating": 0.9}, "GrabFood", "gf_1"
        )
        assert r.rating is None

    def test_source_values_are_used_when_present(self):
        r = _crawled_restaurant(
            {"restaurant_name": "Quán A", "address": "105 Nguyễn Tuân, Thanh Xuân, Hà Nội", "rating": 4.6,
             "delivery_fee": 12000, "delivery_time_mins": 25, "open_hours": "06:00 - 14:00", "cuisine": "Vietnamese"},
            "ShopeeFood", "sf_tx_1",
        )
        assert (r.rating, r.delivery_fee, r.delivery_time_mins, r.open_hours) == (4.6, 12000, 25, "06:00 - 14:00")
        assert r.estimated_fields == []


def test_loaded_data_has_no_invented_values():
    crawled = [r for r in load_restaurants() if r.id.startswith(("sf_", "gf_"))]
    assert all(r.address for r in crawled)
    assert all(r.rating is None or 1.0 <= r.rating <= 5.0 for r in crawled)
    crawled_ids = {r.id for r in crawled}
    assert not [p for p in load_promotions() if p.restaurant_id in crawled_ids]
    crawled_dishes = [d for d in load_menus() if d.restaurant_id in crawled_ids]
    assert all(d.ingredients_source == "description" for d in crawled_dishes)


def test_minimum_rating_filter_excludes_unknown_ratings():
    assert all(r.rating is not None for r in search_restaurants(minimum_rating=4.0))


# ---------------------------------------------------------------------------
# RANK / RESPOND with unknown or estimated values
# ---------------------------------------------------------------------------

def _crawled_candidate() -> RecommendationCandidate:
    rest = Restaurant(id="sf_1", name="Quán A", cuisine="Vietnamese", rating=None, distance_km=2.0,
                      delivery_fee=15000, estimated_fields=["delivery_fee", "delivery_time_mins", "cuisine"])
    dish = Dish(id="d1", restaurant_id="sf_1", name="Phở bò", price=45000,
                ingredients=["bánh phở", "thịt bò"], ingredients_source="description")
    pricing = PricingCalculation(original_price=45000, discount=0, delivery_fee=15000, final_price=60000)
    reasoning = generate_detailed_reasoning(dish, rest, pricing, task_model={"ingredient_excludes": ["hành"]})
    return RecommendationCandidate(dish=dish, restaurant=rest, pricing=pricing, items=[dish], reasoning=reasoning)


def test_unknown_rating_scores_neutral():
    c = _crawled_candidate()
    assert score_candidate(c.dish, c.restaurant, c.pricing)["rating_score"] == 0.0


def test_reasoning_labels_or_omits_estimated_values():
    text = _crawled_candidate().reasoning
    assert "ship ước tính 15,000đ" in text
    assert "phút" not in text          # delivery time is a placeholder
    assert "Ẩm thực" not in text       # cuisine is a guess
    assert "⭐" not in text            # no rating
    assert "🛡️" not in text and "mô tả món không nhắc tới: hành" in text


def test_card_shows_unknown_rating_and_estimated_fee():
    out = format_recommendations_output([_crawled_candidate()])
    assert "chưa có đánh giá" in out
    assert "~15,000đ (ước tính)" in out
