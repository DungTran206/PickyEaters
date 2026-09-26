import json
from typing import Any, Dict, List, Optional
from database.db import (
    get_user_preferences as db_get_preferences,
    set_user_location as db_set_user_location,
    update_user_preference as db_update_preference,
)
from services.search import (
    search_restaurants as svc_search_restaurants,
    search_dishes as svc_search_dishes,
    get_promotions as svc_get_promotions,
    district_label,
    is_locatable,
    get_restaurant_by_id,
    get_dish_by_id
)
from services.pricing import calculate_final_price as svc_calculate_price
from services.recommendation import rank_candidates, format_recommendations_output
from agent.executor import execute_recommendation
from agent.task_model import TaskModel


# ---------------------------------------------------------------------------
# Python tool implementations
# ---------------------------------------------------------------------------

def tool_recommend_dishes_with_radius(
    user_id: str,
    user_address: Optional[str] = None,
    keyword: Optional[str] = None,
    cuisine: Optional[str] = None,
    spicy: Optional[bool] = None,
    disliked_ingredients: Optional[List[str]] = None,
    excluded_concepts: Optional[List[str]] = None,
    task_model: Optional[Dict[str, Any]] = None,
    initial_radius: float = 5.0,
    max_radius: float = 10.0,
    semantic_keywords: Optional[List[str]] = None,
    composition_mode: Optional[str] = None,
    max_final_price: Optional[int] = None,
    exclude_dish_ids: Optional[List[str]] = None,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Adapter for PLAN's recommendation call: runs the bounded search loop
    (agent/executor.py) and formats the structured result.

    Price bounds are not search filters: VALIDATE enforces the TaskModel's hard constraints.
    """
    pref = db_get_preferences(user_id)
    # No default location: PLAN only calls this tool with a locatable address or map point.
    eff_address = user_address or pref.address or ""
    user_coords = (user_lat, user_lng) if user_lat is not None and user_lng is not None else None
    eff_dislikes = disliked_ingredients if disliked_ingredients is not None else pref.disliked_ingredients

    task_obj = None
    if task_model:
        try:
            task_obj = TaskModel(**task_model) if isinstance(task_model, dict) else task_model
        except Exception:
            pass

    result = execute_recommendation(
        task_obj=task_obj,
        task_model=task_model,
        pref=pref,
        user_address=eff_address,
        user_coords=user_coords,
        keyword=keyword,
        cuisine=cuisine,
        spicy=spicy,
        disliked_ingredients=eff_dislikes,
        excluded_concepts=excluded_concepts,
        semantic_keywords=semantic_keywords,
        composition_mode=composition_mode or "single",
        initial_radius=initial_radius,
        max_radius=max_radius,
        max_final_price=max_final_price,
        exclude_dish_ids=exclude_dish_ids or (),
    )
    candidates = result["candidates"]
    replan_action = result["replan_action"]

    formatted = format_recommendations_output(
        candidates=candidates,
        user_pref=pref,
        is_radius_expanded=result["is_radius_expanded"],
        user_address=eff_address,
        replan_action=replan_action,
        search_radius_km=result["search_radius_km"],
        relaxed=result["relaxed"],
    )

    return {
        "status": "success",
        "search_radius_km": result["search_radius_km"],
        "is_radius_expanded": result["is_radius_expanded"],
        "relaxed": result["relaxed"],
        "replan_trace": result["replan_trace"],
        "formatted_text": formatted,
        "candidates": [c.model_dump() for c in candidates],
        "replan_action": replan_action.model_dump() if replan_action else None,
    }


def tool_set_user_location(
    user_id: str,
    address: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Dict[str, Any]:
    """Save the delivery location (typed address or map point). Refuses unlocatable input."""
    coords = (latitude, longitude) if latitude is not None and longitude is not None else None
    if not is_locatable(address, coords):
        return {"status": "rejected", "reason": "location_not_locatable"}
    district = district_label(address, coords)
    label = address.strip() or (f"Vị trí trên bản đồ (gần {district})" if district else "Vị trí trên bản đồ")
    pref = db_set_user_location(user_id, label, district, *(coords or (None, None)))
    return {"status": "success", "address": pref.address, "district": pref.district,
            "latitude": pref.latitude, "longitude": pref.longitude}


def tool_get_user_preferences(user_id: str) -> Dict[str, Any]:
    """Retrieve user food preferences from SQLite database."""
    pref = db_get_preferences(user_id)
    return {
        "user_id": pref.user_id,
        "name": pref.name,
        "address": pref.address,
        "district": pref.district,
        "latitude": pref.latitude,
        "longitude": pref.longitude,
        "preferred_cuisines": pref.preferred_cuisines,
        "preferred_flavors": pref.preferred_flavors,
        "disliked_ingredients": pref.disliked_ingredients,
        "budget": pref.budget,
        "minimum_rating": pref.minimum_rating,
        "preferred_distance": pref.preferred_distance,
        "liked_dishes": pref.liked_dishes,
        "disliked_dishes": pref.disliked_dishes
    }


def tool_search_restaurants(
    location: Optional[str] = None,
    radius_km: Optional[float] = None,
    minimum_rating: Optional[float] = None,
    cuisine: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Search restaurants by location, radius, minimum rating, and cuisine."""
    rests = svc_search_restaurants(
        location=location,
        radius_km=radius_km,
        minimum_rating=minimum_rating,
        cuisine=cuisine
    )
    return [r.model_dump() for r in rests[:10]]


def tool_search_dishes(
    keyword: Optional[str] = None,
    cuisine: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    spicy: Optional[bool] = None,
    restaurant_id: Optional[str] = None,
    disliked_ingredients: Optional[List[str]] = None,
    excluded_concepts: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Search dishes by keyword, cuisine, max_price, spicy flag, or restaurant."""
    dishes = svc_search_dishes(
        keyword=keyword,
        cuisine=cuisine,
        min_price=min_price,
        max_price=max_price,
        spicy=spicy,
        restaurant_id=restaurant_id,
        disliked_ingredients=disliked_ingredients,
        excluded_concepts=excluded_concepts
    )
    return [d.model_dump() for d in dishes[:15]]


def tool_get_promotions(restaurant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve currently available promotions for a restaurant or all restaurants."""
    promos = svc_get_promotions(restaurant_id=restaurant_id)
    return [p.model_dump() for p in promos]


def tool_calculate_final_price(
    dish_price: int,
    promotion_id: Optional[str] = None,
    restaurant_id: Optional[str] = None,
    delivery_fee: Optional[int] = None
) -> Dict[str, Any]:
    """Calculate the final estimated price after applying promotions and delivery fee."""
    actual_fee = delivery_fee if delivery_fee is not None else 15000
    target_promo = None

    if restaurant_id and delivery_fee is None:
        rest = get_restaurant_by_id(restaurant_id)
        if rest:
            actual_fee = rest.delivery_fee

    if promotion_id:
        promos = svc_get_promotions(restaurant_id)
        for p in promos:
            if p.id == promotion_id or p.code == promotion_id:
                target_promo = p
                break

    calc = svc_calculate_price(dish_price, target_promo, delivery_fee=actual_fee)
    return calc.model_dump()


def tool_update_user_preference(
    user_id: str,
    preference_type: str,
    value: Any
) -> Dict[str, Any]:
    """Update persistent user preferences in SQLite when user explicitly states one."""
    updated = db_update_preference(user_id, preference_type, value)
    return {
        "status": "success",
        "message": f"Updated {preference_type} for user {user_id}",
        "preferences": {
            "preferred_cuisines": updated.preferred_cuisines,
            "preferred_flavors": updated.preferred_flavors,
            "disliked_ingredients": updated.disliked_ingredients,
            "budget": updated.budget,
            "minimum_rating": updated.minimum_rating,
            "liked_dishes": updated.liked_dishes
        }
    }


def tool_rank_and_format_recommendations(
    dish_ids: List[str],
    user_id: str,
    task_model: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Rank candidate dishes according to user preferences and format final recommendation."""
    pref = db_get_preferences(user_id)
    dishes = []
    for d_id in dish_ids:
        dish = get_dish_by_id(d_id)
        if dish:
            dishes.append(dish)

    candidates = rank_candidates(dishes, pref, task_model=task_model, top_k=3)
    formatted = format_recommendations_output(candidates, pref)
    return {
        "formatted_text": formatted,
        "candidates": [c.model_dump() for c in candidates]
    }


# ---------------------------------------------------------------------------
# OpenAI Tool Schemas
# ---------------------------------------------------------------------------

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_user_preferences",
            "description": "Retrieve the user's food preferences (cuisines, spicy/flavor, disliked ingredients, budget, rating) from SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "The unique identifier of the user (e.g. 'user_01')"
                    }
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_restaurants",
            "description": "Search available restaurants by location, radius (km), minimum rating, or cuisine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Location or district to search in"},
                    "radius_km": {"type": "number", "description": "Maximum distance radius in km"},
                    "minimum_rating": {"type": "number", "description": "Minimum restaurant rating (1.0 - 5.0)"},
                    "cuisine": {"type": "string", "description": "Cuisine category, e.g. Vietnamese, Korean, Japanese, Thai, Western, Vegetarian"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_dishes",
            "description": "Search available dishes matching keyword, cuisine, budget limit, spicy preference, or restaurant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "Keyword to search in dish name/description, e.g. 'bún bò', 'tokbokki', 'gà rán'"},
                    "cuisine": {"type": "string", "description": "Cuisine type, e.g. Vietnamese, Korean, Japanese, Thai, Western, Vegetarian"},
                    "min_price": {"type": "integer", "description": "Minimum dish price in VND"},
                    "max_price": {"type": "integer", "description": "Maximum dish price in VND"},
                    "spicy": {"type": "boolean", "description": "Filter for spicy (true) or non-spicy (false) dishes"},
                    "restaurant_id": {"type": "string", "description": "Specific restaurant ID to get dishes from"},
                    "disliked_ingredients": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ingredients to exclude from results, e.g. ['onion']"
                    },
                    "excluded_concepts": {"type": "array", "items": {"type": "string"}}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_promotions",
            "description": "Retrieve current discount, percent off, and freeship promotions for a restaurant or all restaurants.",
            "parameters": {
                "type": "object",
                "properties": {
                    "restaurant_id": {
                        "type": "string",
                        "description": "ID of the restaurant, e.g. 'r001'. Leave empty for all promotions."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_final_price",
            "description": "Calculate actual final price taking into account menu price, promotional discounts, and delivery fee.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dish_price": {"type": "integer", "description": "Original price of the dish in VND"},
                    "promotion_id": {"type": "string", "description": "Promotion ID or promotion code to apply"},
                    "restaurant_id": {"type": "string", "description": "Restaurant ID to look up delivery fee and applicable promotions"},
                    "delivery_fee": {"type": "integer", "description": "Estimated delivery fee in VND"}
                },
                "required": ["dish_price"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_preference",
            "description": "Update persistent user preferences in SQLite when user explicitly states a preference (e.g. 'Tao không thích hành', 'Tao thích đồ cay'). Do not call for one-time orders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID to update"},
                    "preference_type": {
                        "type": "string",
                        "enum": ["disliked_ingredients", "preferred_cuisines", "preferred_flavors", "budget", "minimum_rating", "liked_dishes"],
                        "description": "Category of preference being updated"
                    },
                    "value": {
                        "description": "The preference value: ingredient name ('onion'), cuisine ('Korean'), flavor ('spicy'), or budget number (80000)"
                    }
                },
                "required": ["user_id", "preference_type", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_dishes_with_radius",
            "description": "Primary recommendation tool: Searches dishes within initial 5km radius of user's address, scales up to 10km if needed, calculates deals, and generates comprehensive reasoning for each dish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User ID"},
                    "user_address": {"type": "string", "description": "User delivery address (e.g. 'Cầu Giấy, Hà Nội')"},
                    "keyword": {"type": "string", "description": "Food keyword (e.g. 'cơm', 'phở', 'gà rán', 'burger')"},
                    "cuisine": {"type": "string", "description": "Cuisine type (Vietnamese, Korean, Western, etc.)"},
                    "max_price": {"type": "integer", "description": "Max budget in VND"},
                    "min_price": {"type": "integer", "description": "Minimum requested dish price in VND"},
                    "spicy": {"type": "boolean", "description": "Whether spicy is preferred"},
                    "disliked_ingredients": {"type": "array", "items": {"type": "string"}},
                    "excluded_concepts": {"type": "array", "items": {"type": "string"}},
                    "task_model": {"type": "object", "description": "Validated TaskModel"}
                },
                "required": ["user_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rank_and_format_recommendations",
            "description": "Rank found dish IDs against user preferences and produce transparent scores, explanations, and formatted recommendation card.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dish_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of dish IDs found from searching"
                    },
                    "user_id": {"type": "string", "description": "User ID to personalize recommendations for"},
                    "task_model": {"type": "object", "description": "Validated structured task contract"}
                },
                "required": ["dish_ids", "user_id", "task_model"]
            }
        }
    }
]


TOOL_DISPATCHER = {
    "set_user_location": lambda args: tool_set_user_location(
        user_id=args["user_id"],
        address=args.get("address") or "",
        latitude=args.get("latitude"),
        longitude=args.get("longitude"),
    ),
    "get_user_preferences": lambda args: tool_get_user_preferences(args["user_id"]),
    "recommend_dishes_with_radius": lambda args: tool_recommend_dishes_with_radius(
        user_id=args["user_id"],
        user_address=args.get("user_address"),
        user_lat=args.get("user_lat"),
        user_lng=args.get("user_lng"),
        keyword=args.get("keyword"),
        cuisine=args.get("cuisine"),
        spicy=args.get("spicy"),
        disliked_ingredients=args.get("disliked_ingredients"),
        excluded_concepts=args.get("excluded_concepts"),
        task_model=args.get("task_model"),
        initial_radius=args.get("initial_radius", 5.0),
        max_radius=args.get("max_radius", 10.0),
        semantic_keywords=args.get("semantic_keywords"),
        composition_mode=args.get("composition_mode"),
        max_final_price=args.get("max_final_price"),
        exclude_dish_ids=args.get("exclude_dish_ids"),
    ),
    "search_restaurants": lambda args: tool_search_restaurants(
        location=args.get("location"),
        radius_km=args.get("radius_km"),
        minimum_rating=args.get("minimum_rating"),
        cuisine=args.get("cuisine")
    ),
    "search_dishes": lambda args: tool_search_dishes(
        keyword=args.get("keyword"),
        cuisine=args.get("cuisine"),
        min_price=args.get("min_price"),
        max_price=args.get("max_price"),
        spicy=args.get("spicy"),
        restaurant_id=args.get("restaurant_id"),
        disliked_ingredients=args.get("disliked_ingredients"),
        excluded_concepts=args.get("excluded_concepts")
    ),
    "get_promotions": lambda args: tool_get_promotions(restaurant_id=args.get("restaurant_id")),
    "calculate_final_price": lambda args: tool_calculate_final_price(
        dish_price=args["dish_price"],
        promotion_id=args.get("promotion_id"),
        restaurant_id=args.get("restaurant_id"),
        delivery_fee=args.get("delivery_fee")
    ),
    "update_user_preference": lambda args: tool_update_user_preference(
        user_id=args["user_id"],
        preference_type=args["preference_type"],
        value=args["value"]
    ),
    "rank_and_format_recommendations": lambda args: tool_rank_and_format_recommendations(
        dish_ids=args["dish_ids"],
        user_id=args["user_id"],
        task_model=args.get("task_model")
    )
}


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute tool by name and arguments."""
    handler = TOOL_DISPATCHER.get(tool_name)
    if not handler:
        raise ValueError(f"Unknown tool name: {tool_name}")
    return handler(arguments)
