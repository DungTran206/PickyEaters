# -*- coding: utf-8 -*-
"""
COMPOSE layer — builds multi-object orders and composite delivery candidates.

Architecture Rules (AGENTS.md):
- COMPOSE builds multi-object orders.
- Multiple objects are not automatically independent searches.
- Use TaskModel relationships such as same_order or same_restaurant when explicitly represented.
- Budget validation for a composed order happens after composition.
"""

from typing import Any, Dict, List, Optional
from database.models import Dish, Restaurant, PricingCalculation, RecommendationCandidate, UserPreference
from services.pricing import calculate_final_price
from services.search import (
    get_restaurant_by_id,
    get_promotions,
    is_ingredient_disliked,
    normalize_text,
    _match_keyword,
)
from agent.task_model import TaskModel, TaskObject


DRINK_KEYWORDS = ["tra", "nuoc", "coca", "pepsi", "sinh to", "ca phe", "sua chua", "che", "chanh", "quat", "so da", "me", "chan trau", "sua"]
SIDE_KEYWORDS = ["quay", "nem", "canh", "khoai", "cha", "salad", "nom", "kim chi", "banh", "trung", "rau", "sup"]


def match_dish_to_task_object(dish: Dish, obj: TaskObject) -> bool:
    """Check if a dish satisfies a TaskObject (by concept, role, and category)."""
    # Role / category incompatibility check
    if obj.role == "Main" and dish.category in ("Side", "Drink"):
        return False
    if obj.role == "Drink" and dish.category in ("Main", "Side"):
        return False
    if obj.role == "Side" and dish.category == "Drink":
        return False

    norm_name = normalize_text(dish.name)
    norm_desc = normalize_text(dish.description)
    combined = f"{norm_name} {norm_desc}"

    # 1. If explicit concept is specified, match concept
    if obj.concept:
        if _match_keyword(obj.concept, dish.name, dish.description, dish.cuisine):
            return True
        norm_concept = normalize_text(obj.concept)
        if norm_concept in combined:
            return True
        return False

    # 2. If no concept, match by role
    if obj.role == "Drink":
        if dish.category == "Drink":
            return True
        return any(k in norm_name for k in DRINK_KEYWORDS)

    if obj.role == "Side":
        if dish.category == "Side":
            return True
        return any(k in norm_name for k in SIDE_KEYWORDS)

    if obj.role == "Main":
        if dish.category == "Main":
            return True
        return dish.category not in ("Drink", "Side")

    return True


def is_composed_order_request(task: TaskModel) -> bool:
    """Return True if the current task represents a multi-object composite order."""
    if len(task.objects) <= 1:
        return False
    # Explicit relationship
    if any(r.type in ("same_restaurant", "same_order") for r in task.relationships):
        return True
    # Implicit same_restaurant for food delivery: e.g. Main + Drink/Side
    if any(o.role in ("Drink", "Side") for o in task.objects):
        return True
    return False


def compose_candidates(
    task: TaskModel,
    dishes: List[Dish],
    user_address: Optional[str] = None,
    user_pref: Optional[UserPreference] = None,
    restaurants: Optional[List[Restaurant]] = None,
    search_radius_km: float = 5.0,
    is_radius_expanded: bool = False,
) -> List[RecommendationCandidate]:
    """
    Compose single-dish or multi-object delivery candidates from retrieved dishes.
    Enforces same_restaurant grouping and post-composition budget validation.
    """
    if not is_composed_order_request(task):
        return []

    rest_lookup = {r.id: r for r in restaurants} if restaurants else {}

    # Separate Main objects and Secondary objects
    main_objects = [o for o in task.objects if o.role == "Main"]
    if not main_objects and task.objects:
        main_objects = [task.objects[0]]
    secondary_objects = [o for o in task.objects if o not in main_objects]

    # Group dishes by restaurant
    restaurant_dishes: Dict[str, List[Dish]] = {}
    for d in dishes:
        restaurant_dishes.setdefault(d.restaurant_id, []).append(d)

    candidates: List[RecommendationCandidate] = []
    eff_dislikes = (user_pref.disliked_ingredients if user_pref else []) + task.ingredient_excludes

    for r_id, r_dishes in restaurant_dishes.items():
        rest = rest_lookup.get(r_id) or get_restaurant_by_id(r_id, user_address=user_address)
        if not rest:
            continue

        # For each required main object, find matching dishes
        matched_mains = [
            d for d in r_dishes
            if any(match_dish_to_task_object(d, mo) for mo in main_objects)
            and not is_ingredient_disliked(d.ingredients, eff_dislikes)
        ]
        if not matched_mains:
            continue

        # For each required secondary object, find matching dishes
        matched_secondaries_per_obj: List[List[Dish]] = []
        all_secondaries_available = True
        for so in secondary_objects:
            matched_so = [
                d for d in r_dishes
                if match_dish_to_task_object(d, so)
                and not is_ingredient_disliked(d.ingredients, eff_dislikes)
                and d.id not in [m.id for m in matched_mains]
            ]
            if not matched_so and so.required:
                all_secondaries_available = False
                break
            matched_secondaries_per_obj.append(matched_so)

        if not all_secondaries_available:
            continue

        # Select best pair / combination for this restaurant
        best_main = matched_mains[0]
        selected_secondaries = [m_list[0] for m_list in matched_secondaries_per_obj if m_list]
        combo_items = [best_main] + selected_secondaries

        # Calculate combo pricing: one portion of each item per person, one delivery fee
        quantity = task.context.party_size
        subtotal = sum(item.price for item in combo_items) * quantity
        available_promos = get_promotions(r_id)
        best_promo = None
        best_savings = 0
        best_calc = calculate_final_price(subtotal, promotion=None, delivery_fee=rest.delivery_fee)

        for promo in available_promos:
            calc = calculate_final_price(subtotal, promotion=promo, delivery_fee=rest.delivery_fee)
            if calc.savings > best_savings:
                best_savings = calc.savings
                best_promo = promo
                best_calc = calc

        # POST-COMPOSITION BUDGET VALIDATION (Rule 8)
        # price_max applies to the combo's dish subtotal (excluding delivery fee), as in VALIDATE.
        if task.hard_constraints.price_max is not None and subtotal > task.hard_constraints.price_max:
            continue

        if task.hard_constraints.price_min is not None:
            if subtotal < task.hard_constraints.price_min:
                continue

        # Spicy hard constraint validation across combo
        if task.hard_constraints.spicy is not None:
            if task.hard_constraints.spicy is False and any(item.spicy for item in combo_items):
                continue
            if task.hard_constraints.spicy is True and not any(item.spicy for item in combo_items):
                continue

        # Construct combo candidate
        names_str = " + ".join(item.name for item in combo_items)
        candidate = RecommendationCandidate(
            dish=best_main,
            restaurant=rest,
            pricing=best_calc,
            items=combo_items,
            quantity=quantity,
            search_radius_km=search_radius_km,
            is_radius_expanded=is_radius_expanded,
            explanation=f"Combo {names_str} tại {rest.name}"
        )
        candidates.append(candidate)

    return candidates
