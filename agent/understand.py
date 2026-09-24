"""
UNDERSTAND layer — converts raw user text into a validated TaskModel.

Primary path : LLM structured extraction via OpenAI-compatible API.
Fallback path: deterministic regex extraction (used when LLM unavailable).

Public interface (unchanged):
    understand(user_text, last_shown_candidates?) -> TaskModel
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pydantic import ValidationError

from agent.task_model import FollowUp, Relationship, SemanticAttribute, TaskModel, TaskObject
from agent.prompts import UNDERSTAND_SYSTEM_PROMPT
from services.search import normalize_text

load_dotenv()

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment,misc]
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def understand(
    user_text: str,
    last_shown_candidates: Optional[List[Dict[str, Any]]] = None,
) -> TaskModel:
    """Convert one raw user turn into a validated TaskModel.

    Tries LLM extraction first; falls back to regex on any failure.
    Interface is identical regardless of which path runs.
    """
    candidates = last_shown_candidates or []

    # Attempt LLM path
    llm_result = _try_llm_understand(user_text, candidates)
    if llm_result is not None:
        return llm_result

    # Fallback: deterministic regex path
    logger.debug("[understand] Using regex fallback for: %s", user_text[:80])
    return _regex_understand(user_text, candidates)


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------

def _try_llm_understand(
    user_text: str,
    candidates: List[Dict[str, Any]],
) -> Optional[TaskModel]:
    """Call LLM to extract TaskModel. Returns None on any error."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    api_key = groq_key or openai_key
    if not api_key:
        return None  # No credentials → use fallback

    if OpenAI is None:  # package not installed
        logger.warning("[understand] openai package not installed; using regex fallback.")
        return None

    is_groq = bool(groq_key) or api_key.startswith("gsk_")
    default_base = "https://api.groq.com/openai/v1" if is_groq else "https://api.openai.com/v1"
    default_model = "qwen/qwen3.8-27b" if is_groq else "gpt-4o-mini"

    base_url = os.getenv("OPENAI_BASE_URL", default_base)
    model = os.getenv("OPENAI_MODEL_NAME", default_model)

    # Build context hint for follow-up reference resolution
    context_note = ""
    if candidates:
        shown = ", ".join(
            f"#{item.get('ordinal')} {item.get('name', '')}" for item in candidates[:5]
        )
        context_note = f"\n\nCác món vừa hiển thị (để resolve follow-up): {shown}"

    user_message = user_text + context_note

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        # Attempt with response_format=json_object (supported by OpenAI and most providers).
        # Groq supports it for most models; fall back gracefully if the provider rejects it.
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": UNDERSTAND_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
        except Exception as fmt_exc:
            # Some providers / models do not support response_format; fall back to plain chat.
            logger.info(
                "[understand] response_format not supported by provider (%s); retrying without it.",
                fmt_exc,
            )
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": UNDERSTAND_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                max_tokens=600,
            )

        raw = response.choices[0].message.content or ""
        return _parse_and_validate(raw)
    except Exception as exc:
        logger.warning("[understand] LLM call failed (%s); falling back to regex.", exc)
        return None


def _parse_and_validate(raw: str) -> Optional[TaskModel]:
    """Parse LLM output JSON and validate with Pydantic. Returns None on failure.

    Designed to handle both pure JSON responses (from json_object mode) and
    responses that wrap JSON in markdown fences (from plain chat mode).
    """
    # Strip markdown code fences if model wraps the JSON
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()

    # Try direct parse first (expected path when response_format=json_object is used)
    try:
        data = json.loads(cleaned)
        return TaskModel.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        pass

    # Fallback: find first {...} block (handles extra text or reasoning preamble)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        logger.warning("[understand] LLM returned no JSON: %s", raw[:200])
        return None
    try:
        data = json.loads(match.group())
        return TaskModel.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("[understand] TaskModel validation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Regex fallback path (preserved from previous implementation)
# ---------------------------------------------------------------------------

# Hard-coded food terms list used ONLY for regex fallback.
# The LLM path does not rely on this list.
_FOOD_TERMS = [
    ("trà chanh", "tra chanh", "Drink"),
    ("coca", "coca", "Drink"),
    ("cà phê", "ca phe", "Drink"),
    ("sinh tố", "sinh to", "Drink"),
    ("nước cam", "nuoc cam", "Drink"),
    ("trà sữa", "tra sua", "Drink"),
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
    ("bún đậu", "bun dau", "Main"),
    ("phở bò", "pho bo", "Main"),
    ("phở gà", "pho ga", "Main"),
    ("gà rán", "ga ran", "Main"),
    ("tokbokki", "tokbokki", "Main"),
    ("bánh mì", "banh mi", "Main"),
    ("mì xào", "mi xao", "Main"),
    ("phở", "pho", "Main"),
    ("bún", "bun", "Main"),
    ("cơm", "com", "Main"),
    ("gà", "ga", "Main"),
    ("burger", "burger", "Main"),
    ("pizza", "pizza", "Main"),
]

_SEMANTIC_PHRASES = (
    ("do nuoc", "đồ nước"), ("an nhe", "ăn nhẹ"), ("nhe nhe", "nhẹ nhẹ"),
    ("mon thanh", "món thanh"), ("do mat", "đồ mát"), ("mat mat", "mát mát"),
    ("an cho do ngan", "ăn cho đỡ ngán"), ("mon no", "món no"), ("an choi", "ăn chơi"),
    ("thanh thanh", "thanh thanh"),
)


def _regex_understand(
    user_text: str,
    candidates: List[Dict[str, Any]],
) -> TaskModel:
    """Deterministic regex-based extraction. Used as LLM fallback."""
    normalized = normalize_text(user_text).strip()
    result = TaskModel(intent=_regex_intent(normalized))
    if not normalized:
        return result

    _regex_extract_reference(normalized, result, candidates)
    _regex_extract_party_size(normalized, result)
    _regex_extract_price(normalized, result)
    _regex_extract_spicy(normalized, result)
    _regex_extract_exclusions(normalized, result)
    _regex_extract_cuisine_and_priorities(normalized, result)
    _regex_extract_follow_up(normalized, result)
    _regex_extract_objects_and_semantics(normalized, result)
    _regex_add_composition_relationships(normalized, result)

    return TaskModel.model_validate(result.model_dump())


def _contains_term(text: str, token: str) -> bool:
    return bool(re.search(r"\b" + re.escape(token) + r"\b", text))


def _regex_intent(text: str) -> str:
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
    has_food_term = any(_contains_term(text, token) for _, token, _ in _FOOD_TERMS)
    has_semantic = any(phrase in text for phrase, _ in _SEMANTIC_PHRASES)
    request = any(token in text for token in (
        "tim", "muon an", "khong muon an", "khong an", "toi nay an",
        "an gi", "goi y", "mon khac", "re hon", "do han", "do nhat",
        "mon ngon", "mon cay", "do nuoc",
    ))
    if preference and not request:
        return "state_preference"
    if request or has_food_term or has_semantic or re.search(
        r"(?:duoi|khong qua|toi da|tren|hon|tu)\s*\d+", text
    ) or any(token in text for token in (
        "doi qua", "doi bung", "khong cay", "nguoi", "muon com", "muon bun",
        "muon pho", "muon tra", "muon mon", "dang sale",
    )):
        return "request_recommendation"
    return "chit_chat"


def _regex_extract_party_size(text: str, task: TaskModel) -> None:
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


def _regex_extract_price(text: str, task: TaskModel) -> None:
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


def _regex_extract_spicy(text: str, task: TaskModel) -> None:
    if "khong cay" in text or "dung cay" in text:
        task.hard_constraints.spicy = False
    elif re.search(r"\bcay\b", text) and not any(
        x in text for x in ("cay nhe", "cay vua", "cay qua", "mot chut cay")
    ):
        task.hard_constraints.spicy = True
    nuanced_spice = (
        ("cay nhe", "cay nhẹ"), ("cay vua", "cay vừa"),
        ("dung cay qua", "đừng cay quá"), ("mot chut cay", "một chút cay"),
    )
    for phrase, display_text in nuanced_spice:
        if phrase in text:
            task.semantic_attributes.append(_make_semantic_attribute(display_text, "object", text))


def _regex_extract_exclusions(text: str, task: TaskModel) -> None:
    ingredient_terms = {"hanh": "hành", "rau mui": "rau mùi", "ngo": "ngò", "toi": "tỏi", "ot": "ớt"}
    negation = re.search(
        r"(?:khong (?:muon an|an|thich)|tranh|bo|ghet)\s+(.+?)(?:[,?.!]|$)", text
    )
    if not negation:
        return
    excluded = negation.group(1).strip()
    normalized_excluded = normalize_text(excluded)
    ingredient = next(
        (value for key, value in ingredient_terms.items() if key in normalized_excluded), None
    )
    if ingredient:
        task.ingredient_excludes.append(ingredient)
        return
    concept_names = {"com": "cơm", "pho": "phở", "bun": "bún", "thit": "thịt", "ga": "gà"}
    if excluded:
        task.excluded_concepts.append(concept_names.get(normalized_excluded, excluded))


def _regex_extract_cuisine_and_priorities(text: str, task: TaskModel) -> None:
    for phrase, cuisine in (
        ("han", "Korean"), ("nhat", "Japanese"), ("thai", "Thai"), ("viet", "Vietnamese")
    ):
        if (
            re.search(r"\bdo " + re.escape(phrase) + r"\b", text)
            or phrase + " quoc" in text
            or phrase + "ese" in text
        ):
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


def _regex_extract_follow_up(text: str, task: TaskModel) -> None:
    if any(x in text for x in ("re hon nua", "re hon")):
        task.follow_up = FollowUp(type="refine", reason="lower_price")
        if "price" not in task.soft_preferences.priority_order:
            task.soft_preferences.priority_order.append("price")
    elif any(x in text for x in ("dat qua", "mon khac di", "tim cai khac")):
        task.follow_up = FollowUp(
            type="reject_previous",
            reason="too_expensive" if "dat qua" in text else None,
        )
    elif task.intent == "request_recommendation" and not any(
        x in text for x in ("re hon", "dat qua", "mon khac")
    ) and any(x in text for x in ("thoi", "tim ", "toi nay")):
        task.follow_up = FollowUp(type="new_request", reason=None)


def _regex_extract_reference(
    text: str, task: TaskModel, candidates: List[Dict[str, Any]]
) -> None:
    ordinal_match = re.search(r"(?:mon\s+)?so\s+(\d+)", text)
    if ordinal_match:
        ordinal = ordinal_match.group(1)
        if any(str(item.get("ordinal")) == ordinal for item in candidates):
            task.context.conversation_ref = ordinal
    elif "cai nay" in text and len(candidates) == 1:
        task.context.conversation_ref = str(candidates[0].get("ordinal"))


def _regex_extract_objects_and_semantics(text: str, task: TaskModel) -> None:
    if task.intent != "request_recommendation":
        return
    found = []
    for concept, token, role in _FOOD_TERMS:
        excluded = any(normalize_text(value) == token for value in task.excluded_concepts)
        if not excluded and _contains_term(text, token):
            found.append((concept, role))
    if found:
        positions = [
            (text.find(token), concept, token, role)
            for concept, role in found
            for food_concept, token, food_role in _FOOD_TERMS
            if food_concept == concept and food_role == role and text.find(token) >= 0
        ]
        positions = [
            entry for entry in positions
            if not any(
                other_token != entry[2]
                and entry[2] in other_token
                and text.find(other_token) == entry[0]
                for _, _, other_token, _ in positions
            )
        ]
        positions.sort()
        for _, concept, _, role in positions:
            task.objects.append(TaskObject(role=role, concept=concept, required=True))
    else:
        for phrase, display_text in _SEMANTIC_PHRASES:
            if phrase in text:
                if phrase == "do nuoc":
                    task.objects.append(TaskObject(role="Main", concept=None, required=True))
                task.semantic_attributes.append(
                    _make_semantic_attribute(display_text, "object", text)
                )
                break
    for phrase, display_text in (
        ("sang trong", "sang trọng"), ("doi qua", "đói quá"), ("ngon", "ngon")
    ):
        if phrase in text and display_text not in (a.text for a in task.semantic_attributes):
            task.semantic_attributes.append(_make_semantic_attribute(display_text, "object", text))


def _make_semantic_attribute(
    display_text: str, target: str, request_text: str
) -> SemanticAttribute:
    strength = "hard" if any(
        marker in request_text for marker in ("phai ", "nhat dinh", "bat buoc", "nhat thiet")
    ) else "soft"
    return SemanticAttribute(text=display_text, strength=strength, target=target)


def _regex_add_composition_relationships(text: str, task: TaskModel) -> None:
    if len(task.objects) < 2 or not any(
        joiner in text for joiner in (" voi ", " va ", " cung ")
    ):
        return
    task.relationships.append(
        Relationship(type="same_order", objects=list(range(len(task.objects))))
    )
    if any(
        phrase in text
        for phrase in ("cung quan", "cung mot quan", "cung nha hang", "cung mot nha hang")
    ):
        task.relationships.append(
            Relationship(type="same_restaurant", objects=list(range(len(task.objects))))
        )
