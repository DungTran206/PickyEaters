from typing import List, Optional, Dict, Any, Tuple
from database.models import Dish, Restaurant, UserPreference, RecommendationCandidate, PricingCalculation
from services.pricing import calculate_final_price
from services.search import get_restaurant_by_id, get_promotions, is_ingredient_disliked, normalize_text


def evaluate_semantic_match(
    dish: Dish,
    restaurant: Restaurant,
    semantic_attrs: List[Any]
) -> Tuple[float, List[str]]:
    """
    Score dish against qualitative semantic attributes and generate persuasive Vietnamese explanations.
    """
    if not semantic_attrs:
        return 0.0, []

    score = 0.0
    reasons: List[str] = []

    norm_name = normalize_text(dish.name)
    norm_desc = normalize_text(dish.description)
    norm_combined = f"{norm_name} {norm_desc} {normalize_text(dish.cuisine)}"

    for attr in semantic_attrs:
        text = attr.get("text", "") if isinstance(attr, dict) else getattr(attr, "text", "")
        norm_text = normalize_text(text).strip()
        if not norm_text:
            continue

        # 1. Đồ nước / nước dùng
        if norm_text in ("do nuoc", "nuoc nuoc"):
            is_broth = any(w in norm_combined for w in ["pho", "bun", "mien", "chao", "canh", "sup", "hu tieu", "banh canh", "mi van than", "my van than"])
            is_dry = any(w in norm_name for w in ["bun dau", "bun cha", "pho cuon", "pho tron", "mien tron", "mi tron", "banh mi", "xoi", "pizza", "burger", "com"])
            if is_broth and not is_dry:
                score += 3.0
                reasons.append("🍜 Chuẩn điệu món nước: nước dùng nóng hổi, xì xụp đậm đà giải ngấy")
            else:
                score -= 2.0

        # 2. Thanh đạm / nhẹ bụng / dễ nuốt
        elif any(k in norm_text for k in ("thanh dam", "thanh thanh", "nhe bung", "de nuot", "gon nhe")):
            is_light = any(w in norm_combined for w in ["chao", "pho ga", "bun moc", "mien ga", "goi cuon", "salad", "thanh dam", "chay", "canh", "rau"])
            is_heavy = any(w in norm_combined for w in ["thit kho", "mo hanh", "xoi thit", "suon cay", "chien gion", "sot bo", "pate", "ga ran", "pizza", "burger"])
            if is_light:
                score += 2.5
                reasons.append("🍃 Chuẩn vị thanh đạm: thanh nhẹ dễ nuốt, êm bụng không gây ngấy")
            elif is_heavy:
                score -= 2.0

        # 3. Ăn no / chắc bụng / đói bụng
        elif any(k in norm_text for k in ("an no", "chac bung", "doi qua", "doi bung")):
            is_substantial = any(w in norm_combined for w in ["com", "xoi", "mi xao", "bun cha", "bun dau", "ga ran", "suon", "thit kho", "pizza", "burger"])
            if is_substantial:
                score += 2.5
                reasons.append("🍱 Phần ăn chắc bụng: suất ăn no lâu, giàu năng lượng cho người đang đói")

        # 4. Cay nhẹ / hơi cay
        elif any(k in norm_text for k in ("cay nhe", "hoi cay", "cay vua")):
            if dish.spicy or any(w in norm_combined for w in ["cay nhe", "the cay", "sot cay", "hoi cay"]):
                score += 2.0
                reasons.append("🌶️ Độ cay vừa phải: the the tê lưỡi, kích thích vị giác dễ chịu")

        # 5. Ăn trưa nhanh / gọn nhẹ
        elif any(k in norm_text for k in ("an trua nhanh", "nhanh gon", "an nhanh")):
            is_quick = any(w in norm_combined for w in ["banh mi", "com van phong", "bun", "xoi", "goi cuon"])
            if is_quick:
                score += 1.5
                reasons.append("⚡ Bữa ăn nhanh gọn: tiện lợi, đóng hộp sạch sẽ thích hợp ăn trưa văn phòng")

    return score, reasons


def score_candidate(
    dish: Dish,
    restaurant: Restaurant,
    pricing: PricingCalculation,
    user_pref: Optional[UserPreference] = None,
    task_model: Optional[Dict[str, Any]] = None
) -> Dict[str, float]:
    scores = {
        "preference_match": 0.0,
        "request_match": 0.0,
        "price_match": 0.0,
        "distance_score": 0.0,
        "rating_score": 0.0,
        "promotion_score": 0.0,
        "semantic_score": 0.0,
    }

    # 1. Preference Match
    if user_pref:
        if is_ingredient_disliked(dish.ingredients, user_pref.disliked_ingredients):
            scores["preference_match"] = -100.0  # Disqualified
            return scores

        norm_cuisines = [normalize_text(c) for c in user_pref.preferred_cuisines]
        if normalize_text(dish.cuisine) in norm_cuisines or normalize_text(restaurant.cuisine) in norm_cuisines:
            scores["preference_match"] += 2.0

        norm_flavors = [normalize_text(f) for f in user_pref.preferred_flavors]
        if "cay" in norm_flavors or "spicy" in norm_flavors:
            if dish.spicy:
                scores["preference_match"] += 1.5
            else:
                scores["preference_match"] -= 0.5
        elif dish.spicy and ("khong cay" in norm_flavors or "non-spicy" in norm_flavors):
            scores["preference_match"] -= 2.0

        for liked in user_pref.liked_dishes:
            if normalize_text(liked) in normalize_text(dish.name) or normalize_text(dish.name) in normalize_text(liked):
                scores["preference_match"] += 2.5

    # 2. Current Request Match
    if task_model:
        task = task_model if isinstance(task_model, dict) else task_model.model_dump(mode="json")
        concepts = [obj.get("concept") for obj in task.get("objects", []) if obj.get("concept")]
        if any(normalize_text(concept) in normalize_text(dish.name) for concept in concepts):
            scores["request_match"] += 3.0
        cuisines = task.get("soft_preferences", {}).get("cuisine_affinity", [])
        if any(normalize_text(cuisine) in normalize_text(dish.cuisine) for cuisine in cuisines):
            scores["request_match"] += 2.0
        if task.get("hard_constraints", {}).get("spicy") is True and dish.spicy:
            scores["request_match"] += 2.5
        priorities = task.get("soft_preferences", {}).get("priority_order", [])
        if "promotion" in priorities and pricing.savings > 0:
            scores["request_match"] += 2.0

        # Semantic Match
        sem_attrs = task.get("semantic_attributes", [])
        sem_score, _ = evaluate_semantic_match(dish, restaurant, sem_attrs)
        scores["semantic_score"] = sem_score

    # 3. Price / Budget Match
    budget = user_pref.budget if (user_pref and user_pref.budget > 0) else 80000
    if pricing.final_price <= budget:
        scores["price_match"] = 2.5 + max(0.0, (budget - pricing.final_price) / float(budget))
    else:
        over = pricing.final_price - budget
        scores["price_match"] = max(-5.0, -(over / 15000.0))

    # 4. Distance Score (closer is better, scaled up to 10km)
    scores["distance_score"] = round(max(0.0, (10.0 - restaurant.distance_km) / 10.0) * 2.5, 2)

    # 5. Rating Score (4.0 - 5.0 scaled, high priority)
    scores["rating_score"] = round(((restaurant.rating - 3.5) / 1.5) * 4.5, 2)

    # 6. Promotion Score
    if pricing.savings > 0:
        scores["promotion_score"] = 1.5 + round(min(1.5, pricing.savings / 20000.0), 2)

    return scores


def generate_detailed_reasoning(
    dish: Dish,
    restaurant: Restaurant,
    pricing: PricingCalculation,
    user_pref: Optional[UserPreference] = None,
    task_model: Optional[Dict[str, Any]] = None,
    search_radius_km: float = 5.0,
    is_radius_expanded: bool = False
) -> str:
    """
    Generate clear, persuasive Vietnamese reasoning explaining exactly WHY this dish is recommended.
    Always generates at least 3 meaningful points.
    """
    points = []

    # 0. Semantic Reasoning (if matches qualitative descriptors)
    task = task_model if isinstance(task_model, dict) else (task_model.model_dump(mode="json") if task_model else {})
    sem_attrs = task.get("semantic_attributes", [])
    _, sem_reasons = evaluate_semantic_match(dish, restaurant, sem_attrs)
    for sr in sem_reasons:
        points.append(sr)

    # 1. Craving / Request Match
    concepts = [obj.get("concept") for obj in task.get("objects", []) if obj.get("concept")]
    if any(normalize_text(concept) in normalize_text(dish.name) for concept in concepts):
        points.append(f"🎯 Khớp chính xác với yêu cầu: món '{dish.name}' bạn đang tìm")
    elif dish.spicy and task.get("hard_constraints", {}).get("spicy") is True:
        points.append("🌶️ Đúng vị cay nồng bạn yêu cầu")

    # 2. Cuisine preference match
    if user_pref and normalize_text(dish.cuisine) in [normalize_text(c) for c in user_pref.preferred_cuisines]:
        points.append(f"🍜 Chuẩn gu ẩm thực {dish.cuisine} — đúng sở thích của bạn")
    elif dish.cuisine:
        points.append(f"🍽️ Phong cách ẩm thực {dish.cuisine} — đa dạng và phổ biến")

    # 3. Distance & Radius (always included)
    if restaurant.distance_km <= 5.0:
        points.append(
            f"📍 Cách bạn chỉ {restaurant.distance_km}km (trong bán kính 5km) "
            f"— giao hàng ước tính ~{restaurant.delivery_time_mins} phút"
        )
    else:
        points.append(
            f"📍 Cách bạn {restaurant.distance_km}km "
            f"(mở rộng bán kính 10km do khu vực 5km chưa có lựa chọn tối ưu)"
        )

    # 4. Budget & Pricing (always included)
    budget = user_pref.budget if (user_pref and user_pref.budget > 0) else 80000
    if pricing.savings > 0:
        deal_desc = f"giảm {pricing.savings:,}đ"
        if pricing.applied_promotion_code:
            deal_desc += f" (mã '{pricing.applied_promotion_code}')"
        points.append(
            f"💰 Đang có ưu đãi {deal_desc} — "
            f"giá thực tế {pricing.final_price:,}đ (trong ngân sách {budget:,}đ)"
        )
    elif pricing.final_price <= budget:
        points.append(
            f"💵 Giá {pricing.final_price:,}đ — vừa vặn trong ngân sách {budget:,}đ của bạn"
        )
    else:
        over_pct = round((pricing.final_price - budget) / budget * 100)
        points.append(
            f"💵 Giá {pricing.final_price:,}đ "
            f"(vượt ngân sách ~{over_pct}% nhưng chất lượng quán rất xứng đáng)"
        )

    # 5. Disliked ingredients safety check
    if user_pref and user_pref.disliked_ingredients:
        dislikes_str = ", ".join(user_pref.disliked_ingredients)
        points.append(f"🛡️ Đã kiểm tra: không chứa nguyên liệu kiêng ({dislikes_str})")

    # 6. Rating & Platform
    if restaurant.rating >= 4.7:
        points.append(
            f"⭐ Quán được đánh giá rất cao {restaurant.rating}⭐ trên {restaurant.platform}"
        )
    elif restaurant.rating >= 4.4:
        points.append(
            f"⭐ Quán uy tín với {restaurant.rating}⭐ trên {restaurant.platform}"
        )

    return " • ".join(points)


def rank_candidates(
    dishes: List[Dish],
    user_pref: Optional[UserPreference] = None,
    task_model: Optional[Dict[str, Any]] = None,
    user_address: Optional[str] = None,
    search_radius_km: float = 5.0,
    is_radius_expanded: bool = False,
    top_k: int = 4,
    restaurants: Optional[List[Restaurant]] = None,
    precomputed_candidates: Optional[List[RecommendationCandidate]] = None,
) -> List[RecommendationCandidate]:
    candidates = []
    rest_lookup = {r.id: r for r in restaurants} if restaurants else {}

    if precomputed_candidates:
        for c in precomputed_candidates:
            if not c.scores:
                c.scores = score_candidate(c.dish, c.restaurant, c.pricing, user_pref, task_model)
                c.total_score = round(sum(c.scores.values()), 2)
            if not c.reasoning:
                c.reasoning = generate_detailed_reasoning(
                    dish=c.dish,
                    restaurant=c.restaurant,
                    pricing=c.pricing,
                    user_pref=user_pref,
                    task_model=task_model,
                    search_radius_km=search_radius_km,
                    is_radius_expanded=is_radius_expanded
                )
                c.explanation = c.reasoning
            candidates.append(c)
    else:
        for dish in dishes:
            rest = rest_lookup.get(dish.restaurant_id) or get_restaurant_by_id(dish.restaurant_id, user_address=user_address)
            if not rest:
                continue

            # Skip disliked ingredients
            if user_pref and is_ingredient_disliked(dish.ingredients, user_pref.disliked_ingredients):
                continue

            # Find best promo
            available_promos = get_promotions(dish.restaurant_id)
            best_pricing = calculate_final_price(dish.price, None, delivery_fee=rest.delivery_fee)

            for p in available_promos:
                pricing = calculate_final_price(dish.price, p, delivery_fee=rest.delivery_fee)
                if pricing.final_price < best_pricing.final_price:
                    best_pricing = pricing

            scores = score_candidate(dish, rest, best_pricing, user_pref, task_model)
            if scores["preference_match"] < -50:
                continue

            total_score = sum(scores.values())
            reasoning = generate_detailed_reasoning(
                dish=dish,
                restaurant=rest,
                pricing=best_pricing,
                user_pref=user_pref,
                task_model=task_model,
                search_radius_km=search_radius_km,
                is_radius_expanded=is_radius_expanded
            )

            candidate = RecommendationCandidate(
                dish=dish,
                restaurant=rest,
                pricing=best_pricing,
                items=[dish],
                scores=scores,
                total_score=round(total_score, 2),
                explanation=reasoning,
                reasoning=reasoning,
                search_radius_km=search_radius_km,
                is_radius_expanded=is_radius_expanded
            )
            candidates.append(candidate)

    task = task_model if isinstance(task_model, dict) else (task_model.model_dump(mode="json") if task_model else {})
    priorities = task.get("soft_preferences", {}).get("priority_order", [])
    if "rating" in priorities:
        candidates.sort(key=lambda x: (x.restaurant.rating, x.total_score), reverse=True)
    elif "distance" in priorities:
        candidates.sort(key=lambda x: (x.restaurant.distance_km, -x.total_score))
    elif "price" in priorities:
        candidates.sort(key=lambda x: (x.pricing.final_price, -x.total_score))
    else:
        candidates.sort(key=lambda x: x.total_score, reverse=True)

    # Diversity: avoid showing all dishes from only 1 restaurant if multiple restaurants exist
    selected = []
    rest_dish_count = {}

    for c in candidates:
        r_id = c.restaurant.id
        if rest_dish_count.get(r_id, 0) < 1:
            selected.append(c)
            rest_dish_count[r_id] = rest_dish_count.get(r_id, 0) + 1
        if len(selected) >= top_k:
            break

    # If still need more to fill top_k
    if len(selected) < top_k:
        for c in candidates:
            if c not in selected:
                selected.append(c)
                if len(selected) >= top_k:
                    break

    return selected


def format_recommendations_output(
    candidates: List[RecommendationCandidate],
    user_pref: Optional[UserPreference] = None,
    is_radius_expanded: bool = False,
    user_address: str = "",
    replan_action: Optional[Any] = None,
) -> str:
    if not candidates:
        if replan_action and getattr(replan_action, "message_to_user", None):
            return replan_action.message_to_user
        return (
            "Tiếc quá, hiện tại chưa tìm thấy món nào vừa vặn trong bán kính 10km quanh địa chỉ của bạn. "
            "Bạn thử tăng ngân sách hoặc đổi sang món khác xem sao nhé!"
        )

    lines = []
    if is_radius_expanded:
        lines.append(f"🔍 *Thông báo bán kính:* Trong phạm vi 5km quanh '{user_address}' có ít lựa chọn, hệ thống đã **tự động mở rộng bán kính lên 10km** để tìm cho bạn các quán chất lượng nhất!\n")

    lines.append("### 🍜 Các món ngon dành riêng cho bạn:\n")

    for i, c in enumerate(candidates, 1):
        price_k = f"{c.pricing.final_price:,}đ"
        deal_str = ""
        if c.pricing.savings > 0:
            deal_str = f" 🔥 *(Tiết kiệm {c.pricing.savings:,}đ)*"

        # Check if candidate is a multi-item combo
        if c.items and len(c.items) > 1:
            combo_title = " + ".join(it.name for it in c.items)
            lines.append(f"**{i}. Combo: {combo_title} — {c.restaurant.name}**")
            lines.append("- 🍱 **Chi tiết combo:**")
            for it in c.items:
                lines.append(f"  • {it.name}: {it.price:,}đ")
            lines.append(f"- 💵 Tổng đơn: **{price_k}**{deal_str}")
            lines.append(f"- 📍 Khoảng cách: **{c.restaurant.distance_km} km** (Nền tảng: {c.restaurant.platform})")
            lines.append(f"- ⭐ Đánh giá: **{c.restaurant.rating}⭐** | Phí ship chung: {c.pricing.delivery_fee:,}đ")
            lines.append(f"- 💡 **Vì sao chọn combo này:** Tiết kiệm phí ship khi đặt cùng quán • {c.reasoning}")
        else:
            lines.append(f"**{i}. {c.dish.name} — {c.restaurant.name}**")
            lines.append(f"- 💵 Giá: **{price_k}**{deal_str}")
            lines.append(f"- 📍 Khoảng cách: **{c.restaurant.distance_km} km** (Nền tảng: {c.restaurant.platform})")
            lines.append(f"- ⭐ Đánh giá: **{c.restaurant.rating}⭐** | Phí ship: {c.pricing.delivery_fee:,}đ")
            lines.append(f"- 💡 **Vì sao chọn món này:** {c.reasoning}")
        lines.append("")

    lines.append("Bạn ưng món nào nhất trong các món trên? Hay muốn tôi điều chỉnh thêm gì không?")
    return "\n".join(lines)
