from typing import List, Optional, Dict, Any, Tuple
from database.models import Dish, Restaurant, UserPreference, RecommendationCandidate, PricingCalculation
from services.pricing import calculate_final_price
from services.search import get_restaurant_by_id, get_promotions, is_ingredient_disliked, mentions_concept, normalize_text


def evaluate_semantic_match(
    dish: Dish,
    restaurant: Restaurant,
    semantic_attrs: List[Any]
) -> Tuple[float, List[str]]:
    """
    Score dish against qualitative semantic attributes.

    Reasons say which requested attribute matched and on what basis (dish name/description
    keywords or the dish's spicy flag); they never describe taste or texture the data doesn't hold.
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
                reasons.append(f"🍜 Hợp ý \"{text}\": thuộc nhóm món nước (theo tên/mô tả món)")
            else:
                score -= 2.0

        # 2. Thanh đạm / nhẹ bụng / dễ nuốt
        elif any(k in norm_text for k in ("thanh dam", "thanh thanh", "nhe bung", "de nuot", "gon nhe")):
            is_light = any(w in norm_combined for w in ["chao", "pho ga", "bun moc", "mien ga", "goi cuon", "salad", "thanh dam", "chay", "canh", "rau"])
            is_heavy = any(w in norm_combined for w in ["thit kho", "mo hanh", "xoi thit", "suon cay", "chien gion", "sot bo", "pate", "ga ran", "pizza", "burger"])
            if is_light:
                score += 2.5
                reasons.append(f"🍃 Hợp ý \"{text}\": thuộc nhóm món thanh đạm (theo tên/mô tả món)")
            elif is_heavy:
                score -= 2.0

        # 3. Ăn no / chắc bụng / đói bụng
        elif any(k in norm_text for k in ("an no", "chac bung", "doi qua", "doi bung")):
            is_substantial = any(w in norm_combined for w in ["com", "xoi", "mi xao", "bun cha", "bun dau", "ga ran", "suon", "thit kho", "pizza", "burger"])
            if is_substantial:
                score += 2.5
                reasons.append(f"🍱 Hợp ý \"{text}\": thuộc nhóm món chắc bụng (theo tên/mô tả món)")

        # 4. Cay nhẹ / hơi cay
        elif any(k in norm_text for k in ("cay nhe", "hoi cay", "cay vua")):
            mild_hint = next((w for w in ["cay nhe", "hoi cay", "the cay"] if w in norm_combined), None)
            if mild_hint or dish.spicy or "sot cay" in norm_combined:
                score += 2.0
                basis = "mô tả món ghi vị cay nhẹ" if mild_hint else "món được quán đánh dấu là cay, mức độ cay chưa rõ"
                reasons.append(f"🌶️ Hợp ý \"{text}\": {basis}")

        # 5. Ăn trưa nhanh / gọn nhẹ
        elif any(k in norm_text for k in ("an trua nhanh", "nhanh gon", "an nhanh")):
            is_quick = any(w in norm_combined for w in ["banh mi", "com van phong", "bun", "xoi", "goi cuon"])
            if is_quick:
                score += 1.5
                reasons.append(f"⚡ Hợp ý \"{text}\": thuộc nhóm món ăn nhanh (theo tên/mô tả món)")

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
        if any(mentions_concept(concept, dish.name) for concept in concepts):
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

    # 3. Price / Budget Match — budget applies to the dish price (excluding ship), like price_max.
    # The budget stated in this request wins over the profile's soft baseline.
    stated_max = task.get("hard_constraints", {}).get("price_max") if task_model else None
    if stated_max:
        budget = stated_max
    else:
        budget = user_pref.budget if (user_pref and user_pref.budget > 0) else 80000
    dish_total = pricing.original_price
    if dish_total <= budget:
        scores["price_match"] = 2.5 + max(0.0, (budget - dish_total) / float(budget))
    else:
        over = dish_total - budget
        scores["price_match"] = max(-5.0, -(over / 15000.0))

    # 4. Distance Score (closer is better, scaled up to 10km)
    if restaurant.distance_basis != "unknown":  # unknown distance scores neutral (0)
        scores["distance_score"] = round(max(0.0, (10.0 - restaurant.distance_km) / 10.0) * 2.5, 2)

    # 5. Rating Score (4.0 - 5.0 scaled, high priority)
    # Unknown rating scores neutral (0), not a guessed value.
    if restaurant.rating is not None:
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
    is_radius_expanded: bool = False,
    quantity: int = 1,
) -> str:
    """
    Explain WHY this dish is recommended (Vietnamese).

    RESPOND rule: every point must be traceable to structured data — the dish,
    restaurant, pricing, TaskModel or profile. No unsupported claims.
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
    if any(mentions_concept(concept, dish.name) for concept in concepts):
        points.append(f"🎯 Khớp chính xác với yêu cầu: món '{dish.name}' bạn đang tìm")
    elif dish.spicy and task.get("hard_constraints", {}).get("spicy") is True:
        points.append("🌶️ Món được quán đánh dấu là cay, đúng yêu cầu của bạn")

    # 2. Cuisine preference match (profile) or plain cuisine fact — only if the cuisine is source data
    if "cuisine" in restaurant.estimated_fields:
        pass
    elif user_pref and normalize_text(dish.cuisine) in [normalize_text(c) for c in user_pref.preferred_cuisines]:
        points.append(f"🍜 Ẩm thực {dish.cuisine} — đúng sở thích trong hồ sơ của bạn")
    elif dish.cuisine:
        points.append(f"🍽️ Ẩm thực: {dish.cuisine}")

    # 3. Distance & Radius (always included), stating how the distance was obtained
    if restaurant.distance_basis == "stored":
        distance = f"📍 Cách bạn chỉ {restaurant.distance_km}km"
    else:
        distance = f"📍 Khoảng cách: {distance_text(restaurant)}"
    if is_radius_expanded:
        distance += f" (kết quả sau khi mở rộng bán kính lên {search_radius_km:g}km)"
    if "delivery_time_mins" not in restaurant.estimated_fields:
        distance += f" — giao hàng ước tính ~{restaurant.delivery_time_mins} phút"
    points.append(distance)

    # 4. Budget & Pricing (always included).
    # Compare against the budget the user stated in this request; otherwise the profile budget,
    # and say which one it is.
    price_max = task.get("hard_constraints", {}).get("price_max")
    if price_max:
        budget, budget_label = price_max, "ngân sách bạn đặt"
    elif user_pref and user_pref.budget > 0:
        budget, budget_label = user_pref.budget, "ngân sách trong hồ sơ"
    else:
        budget, budget_label = None, ""

    portions = f" cho {quantity} phần" if quantity > 1 else ""
    ship = "ship ước tính" if "delivery_fee" in restaurant.estimated_fields else "ship"
    price_line = f"💵 Giá thực tế {pricing.final_price:,}đ{portions} (gồm {ship} {pricing.delivery_fee:,}đ)"
    if pricing.savings > 0:
        deal_desc = f"giảm {pricing.savings:,}đ"
        if pricing.applied_promotion_code:
            deal_desc += f" mã '{pricing.applied_promotion_code}'"
        price_line = (
            f"💰 Đang có ưu đãi {deal_desc} — giá thực tế {pricing.final_price:,}đ{portions} "
            f"(gồm {ship} {pricing.delivery_fee:,}đ)"
        )
    if budget:
        # Budgets apply to the dish price (menu price x portions, excluding ship).
        dish_total = pricing.original_price
        if dish_total <= budget:
            price_line += f" — giá món {dish_total:,}đ, trong {budget_label} {budget:,}đ"
        else:
            over_pct = round((dish_total - budget) / budget * 100)
            price_line += f" — giá món {dish_total:,}đ, vượt {budget_label} {budget:,}đ khoảng {over_pct}%"
    points.append(price_line)

    # 5. Ingredient-exclusion check: profile dislikes + this request's excludes.
    # Only claim "checked" when the restaurant actually provided ingredient data.
    excludes = list(dict.fromkeys(
        (user_pref.disliked_ingredients if user_pref else []) + task.get("ingredient_excludes", [])
    ))
    if excludes:
        excludes_str = ", ".join(excludes)
        if dish.ingredients and dish.ingredients_source == "menu":
            points.append(f"🛡️ Thành phần món (theo dữ liệu quán) không có: {excludes_str}")
        elif dish.ingredients:
            points.append(
                f"⚠️ Quán chưa cung cấp thành phần; mô tả món không nhắc tới: {excludes_str}"
            )
        else:
            points.append(f"⚠️ Quán chưa cung cấp thành phần món — chưa kiểm tra được: {excludes_str}")

    # 6. Rating & Platform
    if restaurant.rating is None:
        pass
    elif restaurant.rating >= 4.7:
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
    top_k: Optional[int] = 4,
    restaurants: Optional[List[Restaurant]] = None,
    precomputed_candidates: Optional[List[RecommendationCandidate]] = None,
    quantity: int = 1,
) -> List[RecommendationCandidate]:
    """Score and order candidates. top_k=None returns the full ranked list.

    quantity: portions per dish (TaskModel.context.party_size); pricing covers all portions.
    """
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
                    is_radius_expanded=is_radius_expanded,
                    quantity=c.quantity,
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
            subtotal = dish.price * quantity
            best_pricing = calculate_final_price(subtotal, None, delivery_fee=rest.delivery_fee)

            for p in available_promos:
                pricing = calculate_final_price(subtotal, p, delivery_fee=rest.delivery_fee)
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
                is_radius_expanded=is_radius_expanded,
                quantity=quantity,
            )

            candidate = RecommendationCandidate(
                dish=dish,
                restaurant=rest,
                pricing=best_pricing,
                items=[dish],
                quantity=quantity,
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
    candidates.sort(key=priority_sort_key(priorities))

    if top_k is None:
        return candidates
    return select_top_k(candidates, top_k)


# Sort keys for TaskModel.soft_preferences.priority_order (lower = better).
# Values are bucketed so a later priority still decides between options that are
# practically equal on an earlier one (e.g. 52,000đ vs 55,000đ when "rẻ, gần" is asked).
PRICE_BUCKET_VND = 10000
DISTANCE_BUCKET_KM = 1.0
SAVINGS_BUCKET_VND = 5000

PRIORITY_KEYS = {
    "price": lambda c: c.pricing.final_price // PRICE_BUCKET_VND,
    "distance": lambda c: (
        float("inf") if c.restaurant.distance_basis == "unknown"
        else c.restaurant.distance_km // DISTANCE_BUCKET_KM
    ),
    "rating": lambda c: -(c.restaurant.rating if c.restaurant.rating is not None else 0.0),
    "promotion": lambda c: -(c.pricing.savings // SAVINGS_BUCKET_VND),
}


def priority_sort_key(priorities: List[str]):
    """Order by the user's priorities in the order they stated them, then by total_score."""
    keys = [PRIORITY_KEYS[p] for p in dict.fromkeys(priorities) if p in PRIORITY_KEYS]
    return lambda c: tuple(key(c) for key in keys) + (-c.total_score,)


def select_top_k(
    candidates: List[RecommendationCandidate], top_k: int
) -> List[RecommendationCandidate]:
    """Pick top_k from already-ranked candidates, preferring one per restaurant."""
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


def distance_text(restaurant: Restaurant) -> str:
    """Distance with its basis, so an estimate is never presented as a measurement."""
    basis = restaurant.distance_basis
    if basis == "unknown":
        return "chưa rõ khoảng cách"
    if basis == "same_district":
        return f"cùng quận với bạn, ~{restaurant.distance_km:g}km (ước tính)"
    if basis == "district_centroid":
        return f"~{restaurant.distance_km:g}km (ước tính theo quận)"
    return f"{restaurant.distance_km} km"


def _rating_text(restaurant: Restaurant) -> str:
    return f"**{restaurant.rating}⭐**" if restaurant.rating is not None else "chưa có đánh giá"


def _fee_text(candidate: RecommendationCandidate) -> str:
    fee = f"{candidate.pricing.delivery_fee:,}đ"
    return f"~{fee} (ước tính)" if "delivery_fee" in candidate.restaurant.estimated_fields else fee


def format_recommendations_output(
    candidates: List[RecommendationCandidate],
    user_pref: Optional[UserPreference] = None,
    is_radius_expanded: bool = False,
    user_address: str = "",
    replan_action: Optional[Any] = None,
    search_radius_km: Optional[float] = None,
) -> str:
    radius = f"{search_radius_km:g}km" if search_radius_km else "khu vực tìm kiếm"
    if not candidates:
        if replan_action and getattr(replan_action, "message_to_user", None):
            return replan_action.message_to_user
        return (
            f"Tiếc quá, hiện tại chưa tìm thấy món nào phù hợp trong bán kính {radius} quanh địa chỉ của bạn. "
            "Bạn thử tăng ngân sách hoặc đổi sang món khác xem sao nhé!"
        )

    lines = []
    if is_radius_expanded:
        lines.append(f"🔍 *Thông báo bán kính:* Quanh '{user_address}' có ít lựa chọn ở bán kính ban đầu, hệ thống đã **tự động mở rộng bán kính lên {radius}**.\n")

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
                qty = f" × {c.quantity}" if c.quantity > 1 else ""
                lines.append(f"  • {it.name}: {it.price:,}đ{qty}")
            lines.append(f"- 💵 Tổng đơn: **{price_k}**{deal_str}")
            lines.append(f"- 📍 Khoảng cách: **{distance_text(c.restaurant)}** (Nền tảng: {c.restaurant.platform})")
            lines.append(f"- ⭐ Đánh giá: {_rating_text(c.restaurant)} | Phí ship chung: {_fee_text(c)}")
            lines.append(f"- 💡 **Vì sao chọn combo này:** Tiết kiệm phí ship khi đặt cùng quán • {c.reasoning}")
        else:
            lines.append(f"**{i}. {c.dish.name} — {c.restaurant.name}**")
            portions = f" cho {c.quantity} phần ({c.dish.price:,}đ/phần)" if c.quantity > 1 else ""
            lines.append(f"- 💵 Giá: **{price_k}**{portions}{deal_str}")
            lines.append(f"- 📍 Khoảng cách: **{distance_text(c.restaurant)}** (Nền tảng: {c.restaurant.platform})")
            lines.append(f"- ⭐ Đánh giá: {_rating_text(c.restaurant)} | Phí ship: {_fee_text(c)}")
            lines.append(f"- 💡 **Vì sao chọn món này:** {c.reasoning}")
        lines.append("")

    lines.append("Bạn ưng món nào nhất trong các món trên? Hay muốn tôi điều chỉnh thêm gì không?")
    return "\n".join(lines)
