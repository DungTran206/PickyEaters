import pytest
from services.search import (
    load_restaurants,
    load_menus,
    load_promotions,
    search_restaurants,
    search_dishes,
    get_promotions,
    is_ingredient_disliked
)


def test_mock_data_counts():
    rests = load_restaurants()
    dishes = load_menus()
    promos = load_promotions()

    assert len(rests) >= 30, f"Expected at least 30 restaurants, got {len(rests)}"
    assert len(dishes) >= 100, f"Expected at least 100 dishes, got {len(dishes)}"
    assert len(promos) >= 15, f"Expected at least 15 promotions, got {len(promos)}"


def test_search_restaurants_by_cuisine():
    korean_rests = search_restaurants(cuisine="Korean")
    assert len(korean_rests) > 0
    for r in korean_rests:
        assert (
            "korean" in r.cuisine.lower()
            or "korea" in r.name.lower()
            or "hàn quốc" in r.name.lower()
            or "k-pub" in r.name.lower()
            or "dookki" in r.name.lower()
        )


def test_search_restaurants_by_radius_and_rating():
    close_high_rated = search_restaurants(radius_km=2.0, minimum_rating=4.6)
    assert len(close_high_rated) > 0
    for r in close_high_rated:
        assert r.distance_km <= 2.0
        assert r.rating >= 4.6


def test_search_dishes_spicy_and_budget():
    spicy_cheap = search_dishes(spicy=True, max_price=70000)
    assert len(spicy_cheap) > 0
    for d in spicy_cheap:
        assert d.spicy is True
        assert d.price <= 70000


def test_search_dishes_honors_both_price_bounds_and_excluded_concepts():
    filtered = search_dishes(min_price=50000, max_price=100000, excluded_concepts=["cơm"])
    assert filtered
    assert all(50000 <= dish.price <= 100000 for dish in filtered)
    assert all("cơm" not in dish.name.lower() for dish in filtered)


def test_search_dishes_disliked_ingredients():
    # Search all bun bo dishes
    all_bun_bo = search_dishes(keyword="bún bò")
    # Search bun bo dishes with onion excluded
    no_onion_bun_bo = search_dishes(keyword="bún bò", disliked_ingredients=["onion"])

    assert len(all_bun_bo) > len(no_onion_bun_bo)
    for d in no_onion_bun_bo:
        assert not is_ingredient_disliked(d.ingredients, ["onion"])


def test_get_promotions_by_restaurant():
    promos = get_promotions(restaurant_id="r001")
    assert len(promos) >= 1
    assert any("BUNBO20K" in p.code for p in promos)
