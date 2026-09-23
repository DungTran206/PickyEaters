import pytest
from database.models import Promotion
from services.pricing import calculate_final_price


def test_pricing_without_promotion():
    calc = calculate_final_price(dish_price=60000, promotion=None, delivery_fee=15000)
    assert calc.original_price == 60000
    assert calc.discount == 0
    assert calc.delivery_fee == 15000
    assert calc.final_price == 75000
    assert calc.savings == 0


def test_pricing_with_fixed_discount():
    promo = Promotion(
        id="p001",
        restaurant_id="r001",
        code="GIAM20K",
        type="discount",
        value=20000,
        max_discount=20000,
        minimum_order=50000
    )
    # Order meets minimum_order
    calc = calculate_final_price(dish_price=65000, promotion=promo, delivery_fee=12000)
    assert calc.original_price == 65000
    assert calc.discount == 20000
    assert calc.delivery_fee == 12000
    assert calc.final_price == (65000 - 20000) + 12000  # 57000
    assert calc.savings == 20000

    # Order below minimum_order
    calc_under = calculate_final_price(dish_price=40000, promotion=promo, delivery_fee=12000)
    assert calc_under.discount == 0
    assert calc_under.final_price == 40000 + 12000


def test_pricing_with_freeship():
    promo = Promotion(
        id="p002",
        restaurant_id="r001",
        code="FREESHIP15",
        type="freeship",
        value=15000,
        max_discount=15000,
        minimum_order=40000
    )
    calc = calculate_final_price(dish_price=50000, promotion=promo, delivery_fee=12000)
    assert calc.original_price == 50000
    assert calc.delivery_fee == 0  # 12000 - 15000 capped at 0
    assert calc.final_price == 50000
    assert calc.savings == 12000


def test_pricing_with_percentage_and_cap():
    promo = Promotion(
        id="p007",
        restaurant_id="r008",
        code="GIAM15PCT",
        type="percent",
        value=15,
        max_discount=20000,
        minimum_order=60000
    )
    # 80,000 * 15% = 12,000 (below cap)
    calc = calculate_final_price(dish_price=80000, promotion=promo, delivery_fee=15000)
    assert calc.discount == 12000
    assert calc.final_price == (80000 - 12000) + 15000  # 83000

    # 150,000 * 15% = 22,500 -> capped at 20,000
    calc_capped = calculate_final_price(dish_price=150000, promotion=promo, delivery_fee=15000)
    assert calc_capped.discount == 20000
    assert calc_capped.final_price == (150000 - 20000) + 15000  # 145000
