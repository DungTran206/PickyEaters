from typing import Any, Dict, Optional

from agent.task_model import TaskModel


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
    keyword = next((obj.concept for obj in task.objects if obj.concept and obj.role == "Main"), None)
    cuisine = next(iter(task.soft_preferences.cuisine_affinity or profile.get("preferred_cuisines", [])), None)
    return {
        "user_id": user_id,
        "user_address": user_address or profile.get("address"),
        "keyword": keyword,
        "cuisine": cuisine,
        "max_price": task.hard_constraints.price_max,
        "spicy": task.hard_constraints.spicy,
        "disliked_ingredients": list(dict.fromkeys(profile.get("disliked_ingredients", []) + task.ingredient_excludes)),
        "excluded_concepts": task.excluded_concepts,
        "min_price": task.hard_constraints.price_min,
        "initial_radius": profile.get("preferred_distance") or 5.0,
        "max_radius": max(profile.get("preferred_distance") or 5.0, 10.0),
        "task_model": task.model_dump(mode="json"),
    }
