# -*- coding: utf-8 -*-
"""
PLAN layer — translates validated TaskModel + Profile into an actionable execution strategy.

Responsibilities:
1. Multi-object decomposition (Main, Drink, Side, combo, same_restaurant).
2. Semantic category mapping (when user has no specific dish concept, e.g. 'đồ nước', 'thanh thanh', 'nhẹ bụng').
3. Retrieval parameter preparation for ACT tools.
"""

from typing import Any, Dict, List, Optional

from agent.task_model import TaskModel
from services.search import normalize_text

SEMANTIC_CATEGORY_MAP: Dict[str, List[str]] = {
    # Món nước / súp
    "do nuoc": ["pho", "bun", "mien", "hu tieu", "banh canh", "chao", "mi van than", "sup", "canh"],
    "nuoc nuoc": ["pho", "bun", "mien", "hu tieu", "banh canh", "chao", "mi van than", "sup", "canh"],
    # Thanh đạm / nhẹ nhàng
    "thanh dam": ["pho ga", "bun moc", "mien ga", "chao", "goi cuon", "salad", "canh"],
    "thanh thanh": ["pho ga", "bun moc", "mien ga", "chao", "goi cuon", "salad"],
    "de nuot": ["chao", "sup", "mien", "pho"],
    "nhe bung": ["chao", "sup", "mien ga", "pho ga", "goi cuon", "salad"],
    "gon nhe": ["banh mi", "goi cuon", "chao", "mien"],
    "an nhe": ["banh mi", "goi cuon", "salad", "chao", "mien", "banh cuon"],
    "nhe nhe": ["banh mi", "goi cuon", "salad", "chao", "mien", "banh cuon"],
    # Ăn no / chắc bụng
    "an no": ["com", "xoi", "mi xao", "bun dau", "bun cha"],
    "chac bung": ["com", "xoi", "mi xao", "bun cha", "bun dau"],
    "doi qua": ["com", "xoi", "mi xao", "bun cha", "bun dau"],
    "doi bung": ["com", "xoi", "mi xao", "bun cha", "bun dau"],
    # Đồ khô
    "do kho": ["com", "xoi", "banh mi", "bun dau", "bun cha", "mi tron"],
    # Giải cảm / ấm bụng
    "giai cam": ["chao", "chao ga", "chao hanh", "pho ga", "sup"],
    "am bung": ["chao", "pho", "sup"],
    # Ăn xế / ăn vặt / ngọt
    "an vat": ["nem chua ran", "khoai tay chien", "banh trang", "tra sua", "che"],
    "an ngot": ["che", "banh ngot", "tra sua", "sua chua", "caramen"],
    "trang mieng": ["che", "hoa qua", "sua chua", "caramen"],
}


def resolve_semantic_keywords(task: TaskModel) -> List[str]:
    """Map qualitative semantic attributes into search category terms when dish concept is missing."""
    keywords: List[str] = []
    for attr in task.semantic_attributes:
        norm = normalize_text(attr.text).strip()
        for pattern, terms in SEMANTIC_CATEGORY_MAP.items():
            if pattern in norm or norm in pattern:
                for t in terms:
                    if t not in keywords:
                        keywords.append(t)
    return keywords


PRICE_FOLLOW_UP_REASONS = {"lower_price", "too_expensive"}


def merge_follow_up(task: TaskModel, previous: Optional[TaskModel]) -> TaskModel:
    """Carry the previous request forward when the user refines or rejects it.

    "rẻ hơn đi" has no objects of its own; it means "the same request, cheaper".
    Current explicit values win; exclusions accumulate; new_request starts fresh.
    """
    if previous is None or task.follow_up is None or task.follow_up.type == "new_request":
        return task

    merged = previous.model_copy(deep=True)
    merged.intent = task.intent
    merged.follow_up = task.follow_up
    if task.objects:
        merged.objects = task.objects
        merged.relationships = task.relationships
        merged.semantic_attributes = task.semantic_attributes
    else:
        seen = {a.text for a in merged.semantic_attributes}
        merged.semantic_attributes += [a for a in task.semantic_attributes if a.text not in seen]

    current = task.hard_constraints
    if current.price_min is not None or current.price_max is not None:
        merged.hard_constraints.price_min = current.price_min
        merged.hard_constraints.price_max = current.price_max
    if current.spicy is not None:
        merged.hard_constraints.spicy = current.spicy

    merged.ingredient_excludes = list(dict.fromkeys(merged.ingredient_excludes + task.ingredient_excludes))
    merged.excluded_concepts = list(dict.fromkeys(merged.excluded_concepts + task.excluded_concepts))
    if task.soft_preferences.cuisine_affinity:
        merged.soft_preferences.cuisine_affinity = task.soft_preferences.cuisine_affinity
    merged.soft_preferences.priority_order = list(dict.fromkeys(
        task.soft_preferences.priority_order + merged.soft_preferences.priority_order
    ))
    # party_size defaults to 1, so only an explicit different value overrides the previous turn.
    if task.context.party_size != 1:
        merged.context.party_size = task.context.party_size
    merged.context.conversation_ref = task.context.conversation_ref
    return TaskModel.model_validate(merged.model_dump())


def follow_up_constraints(
    task: TaskModel,
    previous_candidates: List[Dict[str, Any]],
    shown_dish_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Derive request-scoped constraints from follow_up + the previously shown candidates.

    - reject_previous → do not show again any dish shown so far in this follow-up chain
      (shown_dish_ids) or in the last results.
    - price-related reason → cheaper (final price incl. ship) than the referenced option:
      the one named by conversation_ref, otherwise the first one shown.
    """
    follow_up = task.follow_up
    if not follow_up or follow_up.type == "new_request" or not previous_candidates:
        return {}

    constraints: Dict[str, Any] = {}
    if follow_up.type == "reject_previous":
        last_shown = [
            item["id"]
            for cand in previous_candidates
            for item in (cand.get("items") or [cand["dish"]])
        ]
        constraints["exclude_dish_ids"] = list(dict.fromkeys((shown_dish_ids or []) + last_shown))
    if follow_up.reason in PRICE_FOLLOW_UP_REASONS:
        ref = task.context.conversation_ref
        index = int(ref) - 1 if ref and ref.isdigit() and 0 < int(ref) <= len(previous_candidates) else 0
        constraints["max_final_price"] = previous_candidates[index]["pricing"]["final_price"] - 1
    return constraints


def plan_recommendation(
    task: TaskModel,
    user_id: str,
    user_address: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
    previous_task: Optional[TaskModel] = None,
    previous_candidates: Optional[List[Dict[str, Any]]] = None,
    shown_dish_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Translate a validated TaskModel, session state and profile into action arguments.

    Session state (previous_task / previous_candidates) is only used to resolve follow-ups;
    the returned "task_model" is the effective task after merging.
    """
    if task.intent != "request_recommendation":
        return None
    profile = profile or {}
    task = merge_follow_up(task, previous_task)

    # Extract primary concept from Main object
    primary_concept = next((obj.concept for obj in task.objects if obj.concept and obj.role == "Main"), None)

    # Extract secondary objects (Drinks, Sides, or other Mains)
    secondary_concepts = [
        obj.concept for obj in task.objects
        if obj.concept and (obj.role != "Main" or obj.concept != primary_concept)
    ]

    # Semantic keyword expansion when primary concept is missing
    semantic_kws: List[str] = []
    if not primary_concept:
        semantic_kws = resolve_semantic_keywords(task)

    # Check composition strategy (same_restaurant / same_order)
    composition_strategy = "independent"
    if any(r.type in ("same_restaurant", "same_order") for r in task.relationships):
        composition_strategy = "same_restaurant"
    elif len(task.objects) > 1 and any(o.role == "Drink" for o in task.objects):
        composition_strategy = "same_restaurant"

    cuisine = next(iter(task.soft_preferences.cuisine_affinity or profile.get("preferred_cuisines", [])), None)

    return {
        "user_id": user_id,
        "user_address": user_address or profile.get("address"),
        "keyword": primary_concept,
        "semantic_keywords": semantic_kws,
        "secondary_keywords": secondary_concepts,
        "composition_strategy": composition_strategy,
        "cuisine": cuisine,
        "max_price": task.hard_constraints.price_max,
        "min_price": task.hard_constraints.price_min,
        "spicy": task.hard_constraints.spicy,
        "disliked_ingredients": list(dict.fromkeys(profile.get("disliked_ingredients", []) + task.ingredient_excludes)),
        "excluded_concepts": task.excluded_concepts,
        "initial_radius": profile.get("preferred_distance") or 5.0,
        "max_radius": max(profile.get("preferred_distance") or 5.0, 10.0),
        "task_model": task.model_dump(mode="json"),
        **follow_up_constraints(task, previous_candidates or [], shown_dish_ids),
    }
