# -*- coding: utf-8 -*-
"""
RE-PLAN layer — bounded strategy loop driven by structured failure/observation state.

Architecture Rules (AGENTS.md):
- RE-PLAN is a bounded strategy loop.
- Do not hard-code one special-case fallback such as only '5 km -> 10 km'.
- Replanning should be driven by structured failure/observation state.
- Hard constraints must not be silently relaxed.
"""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from database.models import RecommendationCandidate
from agent.task_model import TaskModel
from agent.validator import ConstraintViolation


class ReplanAction(BaseModel):
    strategy: str  # "expand_radius" | "suggest_budget_adjustment" | "suggest_alternatives" | "suggest_combo_substitute" | "clarify_concept"
    diagnosis: str
    suggested_budget: Optional[int] = None
    suggested_radius_km: Optional[float] = None
    suggested_alternatives: List[str] = Field(default_factory=list)
    message_to_user: str


def diagnose_and_replan(
    task: TaskModel,
    rejected_candidates: List[Tuple[RecommendationCandidate, List[ConstraintViolation]]],
    current_radius_km: float = 5.0,
    is_radius_expanded: bool = False,
    dishes_retrieved_count: int = 0,
) -> ReplanAction:
    """
    Analyze structured validation failures and retrieval state to decide the next bounded strategy.
    """
    def all_rejected_for(*types: str) -> bool:
        return bool(rejected_candidates) and all(
            any(v.constraint_type in types for v in violations) for _, violations in rejected_candidates
        )

    # 0. Follow-up failures: nothing cheaper than the referenced option / nothing new to show
    if all_rejected_for("follow_up_max_price"):
        limit = next(
            v.expected_value for _, vs in rejected_candidates for v in vs
            if v.constraint_type == "follow_up_max_price"
        )
        cheapest = min(cand.pricing.final_price for cand, _ in rejected_candidates)
        return ReplanAction(
            strategy="suggest_alternatives",
            diagnosis="no_cheaper_option",
            message_to_user=(
                f"Chưa tìm thấy lựa chọn nào rẻ hơn {limit + 1:,}đ cho yêu cầu này "
                f"(rẻ nhất tìm được là {cheapest:,}đ). Bạn có muốn đổi sang món khác không?"
            ),
        )
    if all_rejected_for("previously_shown"):
        return ReplanAction(
            strategy="suggest_alternatives",
            diagnosis="no_new_options",
            message_to_user=(
                "Các lựa chọn phù hợp quanh bạn đều đã được gợi ý ở lượt trước. "
                "Bạn có muốn đổi món, nới ngân sách hoặc bỏ bớt yêu cầu không?"
            ),
        )

    # 1. Check if failure is due to BUDGET (every rejected candidate violates price_max)
    if rejected_candidates:
        if all_rejected_for("price_max"):
            # All available options exceeded the user's budget
            # price_max is compared with the dish price (excluding ship), so report that basis.
            min_avail_price = min(cand.pricing.original_price for cand, _ in rejected_candidates)
            orig_budget = task.hard_constraints.price_max or 0
            
            # Suggest alternative cheaper food categories
            cheaper_alternatives = ["bánh mì", "xôi", "cháo", "bún đậu"]
            concept_name = task.objects[0].concept if task.objects and task.objects[0].concept else "món bạn tìm"

            msg = (
                f"Quanh khu vực của bạn, các quán bán '{concept_name}' hiện có giá món từ {min_avail_price:,}đ (chưa gồm ship) "
                f"(vượt ngân sách {orig_budget:,}đ của bạn). "
                f"Bạn có muốn nới ngân sách lên khoảng {min_avail_price:,}đ, "
                f"hay muốn thử các món vừa túi tiền hơn như {', '.join(cheaper_alternatives[:3])}?"
            )
            return ReplanAction(
                strategy="suggest_budget_adjustment",
                diagnosis="budget_too_tight",
                suggested_budget=min_avail_price,
                suggested_alternatives=cheaper_alternatives,
                message_to_user=msg
            )

    # 2. Check if failure is due to INGREDIENT EXCLUDE (dị ứng / kiêng)
    if rejected_candidates:
        if all_rejected_for("ingredient_exclude", "excluded_concept"):
            # All candidates violated ingredient exclusion
            excluded = task.ingredient_excludes or task.excluded_concepts
            ex_str = ", ".join(excluded)
            concept_name = task.objects[0].concept if task.objects and task.objects[0].concept else "món ăn"
            msg = (
                f"Các lựa chọn '{concept_name}' tìm thấy đều chứa hoặc liên quan đến nguyên liệu bạn kiêng ({ex_str}). "
                f"Để đảm bảo an toàn, hệ thống không gợi ý các món này. Bạn có muốn đổi sang dòng món khác không chứa {ex_str} không?"
            )
            return ReplanAction(
                strategy="suggest_alternatives",
                diagnosis="ingredient_conflict",
                suggested_alternatives=["món luộc/hấp", "cơm phần", "món chay"],
                message_to_user=msg
            )

    # 3. Check if failure is due to DISTANCE / RADIUS (0 restaurants in current radius)
    if dishes_retrieved_count == 0 or len(rejected_candidates) == 0:
        if current_radius_km < 10.0 and not is_radius_expanded:
            return ReplanAction(
                strategy="expand_radius",
                diagnosis="no_restaurants_in_initial_radius",
                suggested_radius_km=10.0,
                message_to_user="Trong bán kính 5km chưa có quán phù hợp, hệ thống đề xuất mở rộng bán kính lên 10km để tìm thêm lựa chọn cho bạn."
            )

    # 4. Check if failure is due to COMBO PAIRING (multi-object same_restaurant failed)
    if len(task.objects) > 1 and any(r.type in ("same_restaurant", "same_order") for r in task.relationships):
        main_concept = task.objects[0].concept or "món chính"
        secondary_concepts = [o.concept for o in task.objects[1:] if o.concept]
        sec_str = ", ".join(secondary_concepts) if secondary_concepts else "món phụ / nước uống"
        msg = (
            f"Hiện không có quán nào có sẵn đồng thời cả '{main_concept}' và '{sec_str}' để giao cùng 1 đơn. "
            f"Bạn có muốn ưu tiên đặt '{main_concept}' trước rồi chọn đồ uống có sẵn tại quán đó không?"
        )
        return ReplanAction(
            strategy="suggest_combo_substitute",
            diagnosis="combo_pair_not_found",
            message_to_user=msg
        )

    # 5. Default fallback: Clarify concept
    concept_str = task.objects[0].concept if task.objects and task.objects[0].concept else "món bạn đang tìm"
    msg = (
        f"Rất tiếc hiện chưa tìm thấy lựa chọn nào đáp ứng trọn vẹn yêu cầu về '{concept_str}' trong bán kính 10km. "
        "Bạn có thể chia sẻ cụ thể hơn hoặc đổi sang loại món khác được không?"
    )
    return ReplanAction(
        strategy="clarify_concept",
        diagnosis="no_matching_options",
        message_to_user=msg
    )
