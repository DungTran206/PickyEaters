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


def plan_recommendation(
    task: TaskModel,
    user_id: str,
    user_address: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Translate a validated TaskModel and available profile into action arguments."""
    if task.intent != "request_recommendation":
        return None
    profile = profile or {}

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
    }
