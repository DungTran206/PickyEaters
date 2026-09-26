# -*- coding: utf-8 -*-
"""
COMPOSE layer — builds multi-object orders and composite delivery candidates.

Architecture Rules (AGENTS.md):
- COMPOSE builds multi-object orders.
- Multiple objects are not automatically independent searches.
- Use TaskModel relationships such as same_order or same_restaurant when explicitly represented.
- Budget validation for a composed order happens after composition.
"""

import itertools
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from database.models import Dish, Restaurant, PricingCalculation, RecommendationCandidate, UserPreference
from services.pricing import best_order_pricing
from services.search import (
    get_restaurant_by_id,
    get_promotions,
    mentions_concept,
    _match_keyword,
)
from agent.planner import composition_mode
from agent.task_model import TaskModel, TaskObject

# Bounds on how many combos COMPOSE produces; RANK and VALIDATE choose among them.
MAX_OPTIONS_PER_SLOT = 4     # cheapest matching dishes considered for each requested slot
MAX_SPLIT_BUNDLES = 12       # cross-restaurant bundles for a same_order request


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

    # 1. If explicit concept is specified, match concept (whole words: "me" must not match "miến")
    if obj.concept:
        return _match_keyword(obj.concept, dish.name, dish.description, dish.cuisine) or mentions_concept(
            obj.concept, f"{dish.name} {dish.description}"
        )

    # 2. If no concept, match by role
    if obj.role == "Drink":
        if dish.category == "Drink":
            return True
        return any(mentions_concept(k, dish.name) for k in DRINK_KEYWORDS)

    if obj.role == "Side":
        if dish.category == "Side":
            return True
        return any(mentions_concept(k, dish.name) for k in SIDE_KEYWORDS)

    if obj.role == "Main":
        if dish.category == "Main":
            return True
        return dish.category not in ("Drink", "Side")

    return True


def unavailable_objects(task: TaskModel, dishes: List[Dish]) -> List[str]:
    """Required objects that no retrieved dish (from any restaurant) can fill — structured
    evidence for RE-PLAN, e.g. ["trà chanh"] when no restaurant in range sells it."""
    return [
        obj.concept or obj.role
        for obj in task.objects
        if obj.required and not any(match_dish_to_task_object(d, obj) for d in dishes)
    ]


def _slot_options(dishes: List[Dish], slot: TaskObject) -> List[Dish]:
    matches = [d for d in dishes if match_dish_to_task_object(d, slot)]
    return sorted(matches, key=lambda d: d.price)[:MAX_OPTIONS_PER_SLOT]


def _fillings(
    slots: List[TaskObject], options_for: Callable[[TaskObject], List[Dish]]
) -> Iterator[List[Dish]]:
    """Every way to fill each requested slot with one distinct dish.

    A required slot with no option makes the order impossible; an optional one is left out.
    """
    option_lists: List[List[Dish]] = []
    for slot in slots:
        options = options_for(slot)
        if options:
            option_lists.append(options)
        elif slot.required:
            return
    for combo in itertools.product(*option_lists):
        if len({d.id for d in combo}) == len(combo):
            yield list(combo)


def _order_pricing(items: List[Dish], restaurant: Restaurant, quantity: int) -> PricingCalculation:
    """One restaurant's order: every item x quantity, one delivery fee, best promotion."""
    subtotal = sum(item.price for item in items) * quantity
    return best_order_pricing(subtotal, restaurant.delivery_fee, get_promotions(restaurant.id))


def _sum_pricing(parts: List[PricingCalculation]) -> PricingCalculation:
    """Total of several restaurants' orders (split order: one delivery fee each)."""
    codes = [p.applied_promotion_code for p in parts if p.applied_promotion_code]
    return PricingCalculation(
        original_price=sum(p.original_price for p in parts),
        discount=sum(p.discount for p in parts),
        delivery_fee=sum(p.delivery_fee for p in parts),
        final_price=sum(p.final_price for p in parts),
        savings=sum(p.savings for p in parts),
        applied_promotion_code=", ".join(codes) or None,
        explanation=" + ".join(p.explanation for p in parts),
    )


def compose_candidates(
    task: TaskModel,
    dishes: List[Dish],
    mode: Optional[str] = None,
    user_address: Optional[str] = None,
    user_pref: Optional[UserPreference] = None,
    restaurants: Optional[List[Restaurant]] = None,
    search_radius_km: float = 5.0,
    is_radius_expanded: bool = False,
    user_coords: Optional[Tuple[float, float]] = None,
) -> List[RecommendationCandidate]:
    """Build order candidates with one distinct dish per requested object (slot).

    mode (from PLAN, defaults to composition_mode(task)):
      - "same_restaurant": every slot from one restaurant (explicit "cùng quán").
      - "same_order": one restaurant preferred; if no restaurant has every slot, split the
        order across restaurants (one delivery fee each, stated in the output).
    Hard constraints (budget, spicy, exclusions) are NOT checked here: VALIDATE checks every
    composed candidate after composition and keeps the evidence for RE-PLAN.
    """
    mode = mode or composition_mode(task)
    if mode == "single":
        return []
    slots = list(task.objects)
    quantity = task.context.party_size
    rest_lookup = {r.id: r for r in restaurants} if restaurants else {}

    def restaurant(r_id: str) -> Optional[Restaurant]:
        return rest_lookup.get(r_id) or get_restaurant_by_id(r_id, user_address=user_address, user_coords=user_coords)

    by_restaurant: Dict[str, List[Dish]] = {}
    for d in dishes:
        by_restaurant.setdefault(d.restaurant_id, []).append(d)

    common = dict(quantity=quantity, search_radius_km=search_radius_km, is_radius_expanded=is_radius_expanded)
    candidates: List[RecommendationCandidate] = []

    # 1. Single-restaurant orders
    for r_id, r_dishes in by_restaurant.items():
        rest = restaurant(r_id)
        if not rest:
            continue
        for items in _fillings(slots, lambda slot: _slot_options(r_dishes, slot)):
            candidates.append(RecommendationCandidate(
                dish=items[0], restaurant=rest, items=items,
                pricing=_order_pricing(items, rest, quantity),
                explanation=f"Combo {' + '.join(i.name for i in items)} tại {rest.name}",
                **common,
            ))

    if candidates or mode != "same_order":
        return candidates

    # 2. Split order: no restaurant has every requested item
    for items in _fillings(slots, lambda slot: _slot_options(dishes, slot)):
        groups: Dict[str, List[Dish]] = {}
        for item in items:
            groups.setdefault(item.restaurant_id, []).append(item)
        rests = [restaurant(r_id) for r_id in groups]
        if len(groups) < 2 or not all(rests):
            continue
        pricing = _sum_pricing([_order_pricing(groups[r.id], r, quantity) for r in rests])
        candidates.append(RecommendationCandidate(
            dish=items[0],
            # The farthest restaurant bounds when the whole order arrives: use it for distance.
            restaurant=max(rests, key=lambda r: r.distance_km),
            restaurants=rests,
            items=items,
            pricing=pricing,
            explanation="Tách đơn: " + " + ".join(i.name for i in items),
            **common,
        ))
        if len(candidates) >= MAX_SPLIT_BUNDLES:
            break
    return candidates
