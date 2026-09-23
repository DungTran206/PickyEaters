from typing import Optional, Union, Dict, Any
from database.models import Promotion, PricingCalculation


def calculate_final_price(
    dish_price: int,
    promotion: Optional[Union[Promotion, Dict[str, Any]]] = None,
    delivery_fee: int = 15000
) -> PricingCalculation:
    """
    Calculates final discounted price and delivery fee based on active promotion.
    """
    if promotion is None:
        return PricingCalculation(
            original_price=dish_price,
            discount=0,
            delivery_fee=delivery_fee,
            final_price=dish_price + delivery_fee,
            applied_promotion_id=None,
            applied_promotion_code=None,
            savings=0,
            explanation=f"Giá món: {dish_price:,}đ + Phí ship: {delivery_fee:,}đ = {dish_price + delivery_fee:,}đ (Không có mã giảm giá)"
        )

    # Convert dict to Promotion object if needed
    if isinstance(promotion, dict):
        promo = Promotion(**promotion)
    else:
        promo = promotion

    discount = 0
    actual_delivery_fee = delivery_fee
    applied_id = None
    applied_code = None
    explanation_parts = []

    # Check minimum order condition
    if dish_price >= promo.minimum_order:
        applied_id = promo.id
        applied_code = promo.code

        if promo.type == "discount":
            discount = int(min(promo.value, dish_price))
            explanation_parts.append(f"Áp mã {promo.code} giảm {discount:,}đ")
        elif promo.type == "freeship":
            ship_discount = int(min(promo.value, delivery_fee))
            actual_delivery_fee = max(0, delivery_fee - ship_discount)
            discount = ship_discount  # tracked as savings
            explanation_parts.append(f"Áp mã freeship {promo.code} giảm ship {ship_discount:,}đ")
        elif promo.type == "percent":
            calc_discount = dish_price * (promo.value / 100.0)
            if promo.max_discount > 0:
                calc_discount = min(calc_discount, promo.max_discount)
            discount = int(calc_discount)
            explanation_parts.append(f"Áp mã {promo.code} giảm {int(promo.value)}% ({discount:,}đ)")
    else:
        explanation_parts.append(f"Đơn chưa đạt tối thiểu {int(promo.minimum_order):,}đ để áp mã {promo.code}")

    if promo.type == "freeship":
        final_price = dish_price + actual_delivery_fee
    else:
        final_price = max(0, dish_price - discount) + actual_delivery_fee

    savings = discount

    summary = (
        f"Giá món: {dish_price:,}đ | "
        + (" ".join(explanation_parts) + " | " if explanation_parts else "")
        + f"Ship: {actual_delivery_fee:,}đ | Tổng thanh toán: {final_price:,}đ"
    )

    return PricingCalculation(
        original_price=dish_price,
        discount=discount,
        delivery_fee=actual_delivery_fee,
        final_price=final_price,
        applied_promotion_id=applied_id,
        applied_promotion_code=applied_code,
        savings=savings,
        explanation=summary
    )
