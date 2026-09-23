import re
from typing import Any, Dict, List, Optional

from agent.task_model import FollowUp, Relationship, SemanticAttribute, TaskModel, TaskObject
from services.search import normalize_text


FOOD_TERMS = [
    ("trà chanh", "tra chanh", "Drink"),
    ("coca", "coca", "Drink"),
    ("xôi chim", "xoi chim", "Main"),
    ("xôi sườn", "xoi suon", "Main"),
    ("xôi gà", "xoi ga", "Main"),
    ("xôi xéo", "xoi xeo", "Main"),
    ("xôi", "xoi", "Main"),
    ("cơm tấm", "com tam", "Main"),
    ("cơm gà", "com ga", "Main"),
    ("cơm sườn", "com suon", "Main"),
    ("bún bò", "bun bo", "Main"),
    ("bún chả", "bun cha", "Main"),
    ("phở bò", "pho bo", "Main"),
    ("phở gà", "pho ga", "Main"),
    ("gà rán", "ga ran", "Main"),
    ("tokbokki", "tokbokki", "Main"),
    ("phở", "pho", "Main"),
    ("bún", "bun", "Main"),
    ("cơm", "com", "Main"),
    ("gà", "ga", "Main"),
    ("burger", "burger", "Main"),
    ("pizza", "pizza", "Main"),
]

SEMANTIC_PHRASES = (
    ("do nuoc", "đồ nước"), ("an nhe", "ăn nhẹ"), ("nhe nhe", "nhẹ nhẹ"),
    ("mon thanh", "món thanh"), ("do mat", "đồ mát"), ("mat mat", "mát mát"),
    ("an cho do ngan", "ăn cho đỡ ngán"), ("mon no", "món no"), ("an choi", "ăn chơi"),
)


def understand(
    user_text: str,
    last_shown_candidates: Optional[List[Dict[str, Any]]] = None,
) -> TaskModel:
    """Convert one raw user turn into a validated structured task."""
    normalized = normalize_text(user_text).strip()
    result = TaskModel(intent=_intent(normalized))
    if not normalized:
        return result

    _extract_reference(normalized, result, last_shown_candidates or [])
    _extract_party_size(normalized, result)
    _extract_price(normalized, result)
    _extract_spicy(normalized, result)
    _extract_exclusions(normalized, result)
    _extract_cuisine_and_priorities(normalized, result)
    _extract_follow_up(normalized, result)
    _extract_objects_and_semantics(normalized, result)
    _add_composition_relationships(normalized, result)

    return TaskModel.model_validate(result.model_dump())


def _intent(text: str) -> str:
    if any(token in text for token in ("xin chao", "hello", "alo", "chao ")) and not any(
        token in text for token in ("an", "mon", "quan", "tim")
    ):
        return "chit_chat"
    if any(token in text for token in ("mo den may gio", "mo cua den", "la mon gi", "la gi vay")):
        return "provide_info"
    preference = any(token in text for token in (
        "tao thich", "minh thich", "toi thich", "tao ghet", "minh ghet", "toi ghet",
        "tao khong thich", "minh khong thich", "toi khong thich",
    ))
    has_food_term = any(_contains_term(text, token) for _, token, _ in FOOD_TERMS)
    has_semantic_food_need = any(phrase in text for phrase, _ in SEMANTIC_PHRASES)
    request = any(token in text for token in ("tim", "muon an", "khong muon an", "khong an", "toi nay an", "an gi", "goi y", "mon khac", "re hon", "do han", "do nhat", "mon ngon", "mon cay", "do nuoc"))
    if preference and not request:
        return "state_preference"
    if request or has_food_term or has_semantic_food_need or re.search(r"(?:duoi|khong qua|toi da|tren|hon|tu)\s*\d+", text) or any(
        token in text for token in ("doi qua", "doi bung", "khong cay", "nguoi", "muon com", "muon bun", "muon pho", "muon tra", "muon mon", "dang sale")
    ):
        return "request_recommendation"
    return "chit_chat"


def _contains_term(text: str, token: str) -> bool:
    return bool(re.search(r"\b" + re.escape(token) + r"\b", text))


def _extract_party_size(text: str, task: TaskModel) -> None:
    match = re.search(r"\b(\d+)\s*(?:nguoi|phan)\b", text)
    if match:
        task.context.party_size = max(1, int(match.group(1)))
    elif "hai nguoi" in text:
        task.context.party_size = 2


def _money(value: str, suffix: str = "") -> int:
    amount = int(value.replace(",", "").replace(".", ""))
    if suffix.lower() == "k" or amount < 1000:
        amount *= 1000
    return amount


def _extract_price(text: str, task: TaskModel) -> None:
    bounds = task.hard_constraints
    range_match = re.search(r"(\d+)\s*k?\s*(?:-|den|toi)\s*(\d+)\s*k", text)
    if range_match:
        bounds.price_min = _money(range_match.group(1))
        bounds.price_max = _money(range_match.group(2), "k")
        return
    match = re.search(r"(?:duoi|khong qua|toi da|tam)\s*(\d+)\s*(k| nghin| ngan)?", text)
    if match:
        bounds.price_max = _money(match.group(1), (match.group(2) or "").strip())
        return
    match = re.search(r"(?:tren|hon|tu)\s*(\d+)\s*(k| nghin| ngan)?", text)
    if match:
        bounds.price_min = _money(match.group(1), (match.group(2) or "").strip())


def _extract_spicy(text: str, task: TaskModel) -> None:
    if "khong cay" in text or "dung cay" in text:
        task.hard_constraints.spicy = False
    elif re.search(r"\bcay\b", text) and not any(x in text for x in ("cay nhe", "cay vua", "cay qua", "mot chut cay")):
        task.hard_constraints.spicy = True
    nuanced_spice = (("cay nhe", "cay nhẹ"), ("cay vua", "cay vừa"),
                     ("dung cay qua", "đừng cay quá"), ("mot chut cay", "một chút cay"))
    for phrase, display_text in nuanced_spice:
        if phrase in text:
            task.semantic_attributes.append(_make_semantic_attribute(display_text, "object", text))


def _extract_exclusions(text: str, task: TaskModel) -> None:
    ingredient_terms = {"hanh": "hành", "rau mui": "rau mùi", "ngo": "ngò", "toi": "tỏi", "ot": "ớt"}
    negation = re.search(r"(?:khong (?:muon an|an|thich)|tranh|bo|ghet)\s+(.+?)(?:[,?.!]|$)", text)
    if not negation:
        return
    excluded = negation.group(1).strip()
    normalized_excluded = normalize_text(excluded)
    ingredient = next((value for key, value in ingredient_terms.items() if key in normalized_excluded), None)
    if ingredient:
        task.ingredient_excludes.append(ingredient)
        return
    concept_names = {"com": "cơm", "pho": "phở", "bun": "bún", "thit": "thịt", "ga": "gà"}
    if excluded:
        task.excluded_concepts.append(concept_names.get(normalized_excluded, excluded))


def _extract_cuisine_and_priorities(text: str, task: TaskModel) -> None:
    for phrase, cuisine in (("han", "Korean"), ("nhat", "Japanese"), ("thai", "Thai"), ("viet", "Vietnamese")):
        if re.search(r"\bdo " + re.escape(phrase) + r"\b", text) or phrase + " quoc" in text or phrase + "ese" in text:
            task.soft_preferences.cuisine_affinity.append(cuisine)
            break
    if any(x in text for x in ("uu tien re", "uu tien gia", "re nhat")):
        task.soft_preferences.priority_order.append("price")
    if any(x in text for x in ("uu tien gan", "gan nhat")):
        task.soft_preferences.priority_order.append("distance")
    if any(x in text for x in ("uu tien rating", "rating cao", "uu tien danh gia")):
        task.soft_preferences.priority_order.append("rating")
    if "uu tien sale" in text or "uu tien khuyen mai" in text or "dang sale" in text:
        task.soft_preferences.priority_order.append("promotion")
    if "dung qua dat" in text:
        task.soft_preferences.priority_order.append("price")


def _extract_follow_up(text: str, task: TaskModel) -> None:
    if any(x in text for x in ("re hon nua", "re hon")):
        task.follow_up = FollowUp(type="refine", reason="lower_price")
        if "price" not in task.soft_preferences.priority_order:
            task.soft_preferences.priority_order.append("price")
    elif any(x in text for x in ("dat qua", "mon khac di", "tim cai khac")):
        task.follow_up = FollowUp(type="reject_previous", reason="too_expensive" if "dat qua" in text else None)
    elif task.intent == "request_recommendation" and not any(x in text for x in ("re hon", "dat qua", "mon khac")) and any(
        x in text for x in ("thoi", "tim ", "toi nay")
    ):
        task.follow_up = FollowUp(type="new_request", reason=None)


def _extract_reference(text: str, task: TaskModel, candidates: List[Dict[str, Any]]) -> None:
    ordinal_match = re.search(r"(?:mon\s+)?so\s+(\d+)", text)
    if ordinal_match:
        ordinal = ordinal_match.group(1)
        if any(str(item.get("ordinal")) == ordinal for item in candidates):
            task.context.conversation_ref = ordinal
    elif "cai nay" in text and len(candidates) == 1:
        task.context.conversation_ref = str(candidates[0].get("ordinal"))


def _extract_objects_and_semantics(text: str, task: TaskModel) -> None:
    if task.intent != "request_recommendation":
        return
    found = []
    for concept, token, role in FOOD_TERMS:
        excluded = any(normalize_text(value) == token for value in task.excluded_concepts)
        if not excluded and _contains_term(text, token):
            found.append((concept, role))
    if found:
        # Keep user mention order, with specific dishes before their broader category.
        positions = [
            (text.find(token), concept, token, role)
            for concept, role in found
            for food_concept, token, food_role in FOOD_TERMS
            if food_concept == concept and food_role == role and text.find(token) >= 0
        ]
        positions = [entry for entry in positions if not any(
            other_token != entry[2] and entry[2] in other_token and text.find(other_token) == entry[0]
            for _, _, other_token, _ in positions
        )]
        positions.sort()
        for _, concept, _, role in positions:
            task.objects.append(TaskObject(role=role, concept=concept, required=True))
    else:
        for phrase, display_text in SEMANTIC_PHRASES:
            if phrase in text:
                if phrase == "do nuoc":
                    task.objects.append(TaskObject(role="Main", concept=None, required=True))
                task.semantic_attributes.append(_make_semantic_attribute(display_text, "object", text))
                break
    if "ngoi lau duoc" in text:
        task.semantic_attributes.append(_make_semantic_attribute("ngồi lâu được", "venue", text))
    for phrase, display_text in (("sang trong", "sang trọng"), ("doi qua", "đói quá"), ("ngon", "ngon")):
        if phrase in text and display_text not in (attribute.text for attribute in task.semantic_attributes):
            task.semantic_attributes.append(_make_semantic_attribute(display_text, "object", text))


def _make_semantic_attribute(display_text: str, target: str, request_text: str) -> SemanticAttribute:
    strength = "hard" if any(
        marker in request_text for marker in ("phai ", "nhat dinh", "bat buoc", "nhat thiet")
    ) else "soft"
    return SemanticAttribute(text=display_text, strength=strength, target=target)


def _add_composition_relationships(text: str, task: TaskModel) -> None:
    if len(task.objects) < 2 or not any(joiner in text for joiner in (" voi ", " va ", " cung ")):
        return
    task.relationships.append(Relationship(type="same_order", objects=list(range(len(task.objects)))))
    if any(phrase in text for phrase in ("cung quan", "cung mot quan", "cung nha hang", "cung mot nha hang")):
        task.relationships.append(Relationship(type="same_restaurant", objects=list(range(len(task.objects)))))
