# -*- coding: utf-8 -*-
"""
Recommendation execution loop — orchestration only:

    ACT (search_within_radius) → COMPOSE → RANK → VALIDATE → OBSERVE → RE-PLAN (bounded)

Each stage is delegated to its own layer; this module only sequences them and records a
structured trace of every search attempt (radius, soft preferences, counts, next step).
Hard constraints come from the TaskModel and are enforced by VALIDATE on every attempt;
RE-PLAN may only change the search radius and soft preferences.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent.composer import compose_candidates, unavailable_objects
from agent.replan import SearchState, apply_step, diagnose_and_replan, next_step, radius_schedule
from agent.task_model import TaskModel
from agent.validator import ConstraintViolation, validate_candidates_list
from database.models import RecommendationCandidate, UserPreference
from services.recommendation import rank_candidates, select_top_k
from services.search import search_within_radius

TOP_K = 4

Rejected = List[Tuple[RecommendationCandidate, List[ConstraintViolation]]]


def build_valid_candidates(
    task_obj: Optional[TaskModel],
    task_model: Optional[Dict[str, Any]],
    pref: UserPreference,
    search_res: Dict[str, Any],
    mode: str,
    user_address: str,
    user_coords: Optional[Tuple[float, float]],
    is_radius_expanded: bool,
    max_final_price: Optional[int] = None,
    exclude_dish_ids: Sequence[str] = (),
) -> Tuple[List[RecommendationCandidate], Rejected]:
    """COMPOSE (multi-object) → RANK all → VALIDATE all. Returns (valid ranked, rejected).

    Validation runs on the full ranked list, so a valid lower-ranked option is never lost
    because invalid ones would have occupied the top_k slots.
    """
    radius = search_res["search_radius_km"]
    rank_args = dict(
        user_pref=pref, task_model=task_model, user_address=user_address,
        search_radius_km=radius, is_radius_expanded=is_radius_expanded, top_k=None,
    )
    if task_obj and mode != "single":
        composed = compose_candidates(
            task=task_obj, dishes=search_res["dishes"], mode=mode, user_address=user_address,
            restaurants=search_res["restaurants"], search_radius_km=radius,
            is_radius_expanded=is_radius_expanded, user_coords=user_coords,
        )
        ranked = rank_candidates(dishes=[], precomputed_candidates=composed, **rank_args) if composed else []
    else:
        quantity = task_obj.context.party_size if task_obj else 1
        ranked = rank_candidates(
            dishes=search_res["dishes"], restaurants=search_res["restaurants"], quantity=quantity, **rank_args
        )

    if not task_obj:
        return ranked, []
    return validate_candidates_list(
        ranked, task_obj, pref, max_final_price=max_final_price, exclude_dish_ids=exclude_dish_ids
    )


def execute_recommendation(
    task_obj: Optional[TaskModel],
    task_model: Optional[Dict[str, Any]],
    pref: UserPreference,
    user_address: str,
    user_coords: Optional[Tuple[float, float]] = None,
    keyword: Optional[str] = None,
    cuisine: Optional[str] = None,
    spicy: Optional[bool] = None,
    disliked_ingredients: Optional[List[str]] = None,
    excluded_concepts: Optional[List[str]] = None,
    semantic_keywords: Optional[List[str]] = None,
    composition_mode: str = "single",
    initial_radius: float = 5.0,
    max_radius: float = 10.0,
    max_final_price: Optional[int] = None,
    exclude_dish_ids: Sequence[str] = (),
    top_k: int = TOP_K,
) -> Dict[str, Any]:
    """Run search attempts until RE-PLAN stops, then return the best valid options.

    Larger radii and relaxed soft preferences only ever add options, so the last attempt
    is the most complete one.
    """
    mode = composition_mode if task_obj else "single"
    state = SearchState(
        radius_km=initial_radius,
        radii=radius_schedule(initial_radius, max_radius),
        cuisine=cuisine,
        cuisine_relaxable=bool(keyword or semantic_keywords or mode != "single"),
    )

    while True:
        is_expanded = state.radius_km > initial_radius
        search_res = search_within_radius(
            radius_km=state.radius_km,
            user_address=user_address,
            user_coords=user_coords,
            keyword=keyword,
            cuisine=state.active_cuisine,
            spicy=spicy,
            disliked_ingredients=disliked_ingredients,
            excluded_concepts=excluded_concepts,
            semantic_keywords=semantic_keywords,
            all_dishes=mode != "single",
        )
        valid, rejected = build_valid_candidates(
            task_obj, task_model, pref, search_res, mode, user_address, user_coords, is_expanded,
            max_final_price=max_final_price, exclude_dish_ids=exclude_dish_ids,
        )
        step = next_step(state, len(valid))
        state.trace.append({
            "radius_km": state.radius_km,
            "cuisine": state.active_cuisine,
            "retrieved_dishes": len(search_res["dishes"]),
            "valid": len(valid),
            "rejected": len(rejected),
            "next_step": step.model_dump() if step else None,
        })
        if step is None:
            break
        state = apply_step(state, step)

    candidates = select_top_k(valid, top_k)
    replan_action = None
    if not candidates and task_obj:
        replan_action = diagnose_and_replan(
            task=task_obj,
            rejected_candidates=rejected,
            current_radius_km=state.radius_km,
            is_radius_expanded=is_expanded,
            dishes_retrieved_count=len(search_res["dishes"]),
            max_radius_km=max_radius,
            unavailable_objects=unavailable_objects(task_obj, search_res["dishes"]) if mode != "single" else None,
        )

    return {
        "candidates": candidates,
        "search_radius_km": state.radius_km,
        "is_radius_expanded": is_expanded,
        "relaxed": state.relaxed,
        "replan_trace": state.trace,
        "replan_action": replan_action,
    }
