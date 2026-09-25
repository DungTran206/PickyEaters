# -*- coding: utf-8 -*-
"""
VALIDATE layer — enforces hard-constraint checking and produces structured violation evidence.

Architecture Rules (AGENTS.md):
- VALIDATE owns hard-constraint checking.
- Hard constraints must not be silently relaxed.
- Replanning may change search strategy or soft preferences, but must not violate hard exclusions/constraints.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple
from pydantic import BaseModel, Field
from database.models import Dish, Restaurant, UserPreference, RecommendationCandidate
from services.search import is_ingredient_disliked, mentions_concept
from agent.task_model import TaskModel


class ConstraintViolation(BaseModel):
    # "price_max", "price_min", "spicy", "ingredient_exclude", "excluded_concept",
    # "follow_up_max_price", "previously_shown"
    constraint_type: str
    field: str
    message: str
    actual_value: Any = None
    expected_value: Any = None


class ValidationResult(BaseModel):
    is_valid: bool
    violations: List[ConstraintViolation] = Field(default_factory=list)


def validate_candidate(
    candidate: RecommendationCandidate,
    task: TaskModel,
    user_pref: Optional[UserPreference] = None,
    max_final_price: Optional[int] = None,
    exclude_dish_ids: Sequence[str] = (),
) -> ValidationResult:
    """
    Validate a recommendation candidate (single dish or composed combo) against hard constraints.
    Returns ValidationResult with detailed, structured violations if any exist.

    max_final_price / exclude_dish_ids are follow-up constraints derived by PLAN from
    session state ("rẻ hơn" → cheaper than the referenced option; "món khác" → not shown before).
    """
    violations: List[ConstraintViolation] = []

    # All dishes involved in this candidate
    items = candidate.items if candidate.items else [candidate.dish]
    eff_price = candidate.pricing.final_price
    eff_subtotal = candidate.pricing.original_price

    # 1. Hard constraint: price_max
    if task.hard_constraints.price_max is not None:
        max_p = task.hard_constraints.price_max
        # For food delivery orders, check if both subtotal and final price exceed budget
        if eff_subtotal > max_p and eff_price > max_p:
            violations.append(ConstraintViolation(
                constraint_type="price_max",
                field="price",
                message=f"Giá thực tế {eff_price:,}đ vượt quá ngân sách tối đa {max_p:,}đ",
                actual_value=eff_price,
                expected_value=max_p
            ))

    # 2. Hard constraint: price_min
    if task.hard_constraints.price_min is not None:
        min_p = task.hard_constraints.price_min
        if eff_subtotal < min_p:
            violations.append(ConstraintViolation(
                constraint_type="price_min",
                field="price",
                message=f"Giá {eff_subtotal:,}đ thấp hơn mức giá tối thiểu {min_p:,}đ",
                actual_value=eff_subtotal,
                expected_value=min_p
            ))

    # 3. Hard constraint: spicy
    if task.hard_constraints.spicy is not None:
        desired_spicy = task.hard_constraints.spicy
        if desired_spicy is False:
            spicy_items = [d.name for d in items if d.spicy]
            if spicy_items:
                violations.append(ConstraintViolation(
                    constraint_type="spicy",
                    field="spicy",
                    message=f"Yêu cầu không cay nhưng món '{', '.join(spicy_items)}' lại là món cay",
                    actual_value=True,
                    expected_value=False
                ))
        elif desired_spicy is True:
            has_spicy = any(d.spicy for d in items)
            if not has_spicy:
                violations.append(ConstraintViolation(
                    constraint_type="spicy",
                    field="spicy",
                    message="Yêu cầu món cay nhưng đơn hàng không có món cay nào",
                    actual_value=False,
                    expected_value=True
                ))

    # 4. Hard constraint: ingredient_excludes & user_pref.disliked_ingredients
    all_dislikes = list(dict.fromkeys(
        (user_pref.disliked_ingredients if user_pref else []) + task.ingredient_excludes
    ))
    if all_dislikes:
        for d in items:
            if is_ingredient_disliked(d.ingredients, all_dislikes):
                violations.append(ConstraintViolation(
                    constraint_type="ingredient_exclude",
                    field="ingredients",
                    message=f"Món '{d.name}' chứa nguyên liệu kiêng trong thành phần",
                    actual_value=d.ingredients,
                    expected_value=all_dislikes
                ))

    # 5. Hard constraint: excluded_concepts (e.g. user said "không ăn cơm" -> excludes cơm)
    if task.excluded_concepts:
        for d in items:
            combined_text = f"{d.name} {d.description} {d.category}"
            for ec in task.excluded_concepts:
                if mentions_concept(ec, combined_text):
                    violations.append(ConstraintViolation(
                        constraint_type="excluded_concept",
                        field="concept",
                        message=f"Món '{d.name}' vi phạm yêu cầu loại trừ món '{ec}'",
                        actual_value=d.name,
                        expected_value=f"not {ec}"
                    ))

    # 6. Follow-up: must be cheaper than the referenced previous option (total incl. ship)
    if max_final_price is not None and eff_price > max_final_price:
        violations.append(ConstraintViolation(
            constraint_type="follow_up_max_price",
            field="price",
            message=f"Giá thực tế {eff_price:,}đ không rẻ hơn lựa chọn trước ({max_final_price + 1:,}đ)",
            actual_value=eff_price,
            expected_value=max_final_price,
        ))

    # 7. Follow-up: user rejected the previously shown options
    shown = [d.name for d in items if d.id in exclude_dish_ids]
    if shown:
        violations.append(ConstraintViolation(
            constraint_type="previously_shown",
            field="dish_id",
            message=f"Món '{', '.join(shown)}' đã được gợi ý ở lượt trước",
            actual_value=[d.id for d in items],
            expected_value=list(exclude_dish_ids),
        ))

    return ValidationResult(
        is_valid=len(violations) == 0,
        violations=violations
    )


def validate_candidates_list(
    candidates: List[RecommendationCandidate],
    task: TaskModel,
    user_pref: Optional[UserPreference] = None,
    max_final_price: Optional[int] = None,
    exclude_dish_ids: Sequence[str] = (),
) -> Tuple[List[RecommendationCandidate], List[Tuple[RecommendationCandidate, List[ConstraintViolation]]]]:
    """
    Validate all candidates, returning (valid_candidates, rejected_candidates_with_violations).
    Preserves structured failure evidence for RE-PLAN.
    """
    valid: List[RecommendationCandidate] = []
    rejected: List[Tuple[RecommendationCandidate, List[ConstraintViolation]]] = []

    for c in candidates:
        res = validate_candidate(c, task, user_pref, max_final_price, exclude_dish_ids)
        if res.is_valid:
            valid.append(c)
        else:
            rejected.append((c, res.violations))

    return valid, rejected
