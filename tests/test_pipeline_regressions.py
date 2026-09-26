# -*- coding: utf-8 -*-
"""
Regression tests for two pipeline contract bugs:

1. excluded_concepts must match whole words, not substrings
   ("gà" must not exclude "béo ngậy" / "bánh gạo"; "cơm" must not exclude "Combo").
2. VALIDATE must run on the full ranked list before top_k selection, so valid
   lower-ranked candidates are not lost when invalid ones rank higher.
"""

import pytest

import agent.executor as executor
import agent.tools as tools
from agent.task_model import HardConstraints, TaskModel, TaskObject
from agent.validator import validate_candidate
from database.models import Dish, PricingCalculation, RecommendationCandidate, Restaurant, UserPreference
from services.search import mentions_concept, search_dishes


# ---------------------------------------------------------------------------
# 1. Whole-word excluded_concepts matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("concept, text, expected", [
    ("gà", "Cơm gà xối mỡ", True),
    ("gà", "Gà rán giòn", True),
    ("gà", "Đậu phụ rán béo ngậy", False),      # ngậy -> ngay contains "ga"
    ("gà", "Bánh gạo cay", False),               # gạo -> gao contains "ga"
    ("cơm", "Combo trà sữa", False),             # combo contains "com"
    ("cơm", "Cơm tấm sườn", True),
    ("xôi xéo", "Xôi xéo hành phi", True),
    ("xôi xéo", "Xôi gà", False),
    ("", "anything", False),
])
def test_mentions_concept_is_whole_word(concept, text, expected):
    assert mentions_concept(concept, text) is expected


def _candidate(name: str, description: str) -> RecommendationCandidate:
    dish = Dish(id="d1", restaurant_id="r1", name=name, price=40000, description=description)
    rest = Restaurant(id="r1", name="Quán", cuisine="Vietnamese", rating=4.5, distance_km=1.0, delivery_fee=15000)
    pricing = PricingCalculation(original_price=40000, discount=0, delivery_fee=15000, final_price=55000)
    return RecommendationCandidate(dish=dish, restaurant=rest, pricing=pricing, items=[dish])


def test_validator_does_not_reject_substring_lookalikes():
    task = TaskModel(intent="request_recommendation", excluded_concepts=["gà"])
    assert validate_candidate(_candidate("Đậu phụ rán", "ngoài giòn trong béo ngậy"), task).is_valid
    assert not validate_candidate(_candidate("Cơm gà", "gà luộc"), task).is_valid


def test_search_exclusion_keeps_dishes_without_the_concept():
    all_dishes = search_dishes()
    kept_ids = {d.id for d in search_dishes(excluded_concepts=["gà"])}
    wrongly_dropped = [
        d.name for d in all_dishes
        if d.id not in kept_ids and not mentions_concept("gà", f"{d.name} {d.description} {d.category}")
    ]
    assert wrongly_dropped == []
    # And every kept dish really is free of the concept.
    assert all(
        not mentions_concept("gà", f"{d.name} {d.description} {d.category}")
        for d in all_dishes if d.id in kept_ids
    )


# ---------------------------------------------------------------------------
# 2. VALIDATE before top_k selection
# ---------------------------------------------------------------------------

def test_valid_candidate_below_top_k_is_not_lost(monkeypatch):
    # Four spicy dishes at top-rated restaurants outrank one non-spicy dish at a
    # low-rated restaurant. The user requires non-spicy, so only the last is valid.
    restaurants = [
        Restaurant(id=f"r{i}", name=f"Quán {i}", cuisine="Vietnamese",
                   rating=4.9, distance_km=1.0, delivery_fee=15000)
        for i in range(4)
    ] + [Restaurant(id="r_ok", name="Quán ổn", cuisine="Vietnamese",
                    rating=3.6, distance_km=4.0, delivery_fee=15000)]
    dishes = [
        Dish(id=f"d{i}", restaurant_id=f"r{i}", name="Bún bò cay", price=50000, spicy=True)
        for i in range(4)
    ] + [Dish(id="d_ok", restaurant_id="r_ok", name="Bún bò", price=50000, spicy=False)]

    monkeypatch.setattr(
        executor, "search_within_radius",
        lambda radius_km, **_: {"dishes": dishes, "restaurants": restaurants, "search_radius_km": radius_km},
    )
    monkeypatch.setattr(tools, "db_get_preferences", lambda user_id: UserPreference(user_id=user_id))

    task = TaskModel(
        intent="request_recommendation",
        objects=[TaskObject(role="Main", concept="bún bò")],
        hard_constraints=HardConstraints(spicy=False),
    )
    result = tools.tool_recommend_dishes_with_radius(
        user_id="t", user_address="Cầu Giấy, Hà Nội", keyword="bún bò",
        task_model=task.model_dump(mode="json"),
    )

    assert [c["dish"]["id"] for c in result["candidates"]] == ["d_ok"]
    assert result["replan_action"] is None


# ---------------------------------------------------------------------------
# 3. RESPOND: reasoning only states facts traceable to structured data
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock

from agent.agent import FoodAgent, _numbers
from services.recommendation import format_recommendations_output, generate_detailed_reasoning


def _reasoning(dish=None, rest=None, final_price=55000, pref=None, task=None, **kw):
    dish = dish or Dish(id="d1", restaurant_id="r1", name="Bún bò", price=40000, ingredients=["bò", "bún"])
    rest = rest or Restaurant(id="r1", name="Quán", cuisine="Vietnamese", rating=4.5,
                              distance_km=1.5, delivery_fee=15000)
    pricing = PricingCalculation(original_price=final_price - 15000, discount=0,
                                 delivery_fee=15000, final_price=final_price)
    return generate_detailed_reasoning(dish, rest, pricing, user_pref=pref, task_model=task or {}, **kw)


def test_budget_line_uses_stated_price_max_not_profile_budget():
    pref = UserPreference(user_id="u", budget=80000)
    # dish 45k + ship 15k; stated budget 40k applies to the dish price
    text = _reasoning(final_price=60000, pref=pref, task={"hard_constraints": {"price_max": 40000}})
    assert "40,000đ" in text and "80,000đ" not in text
    assert "vượt ngân sách bạn đặt" in text
    assert "xứng đáng" not in text  # no unsupported quality claim


def test_price_max_applies_to_dish_price_not_total_with_ship():
    # "dưới 60k": a 60k dish is within budget even though the total with ship is 76k.
    from agent.task_model import TaskModel, HardConstraints
    task = TaskModel(intent="request_recommendation", hard_constraints=HardConstraints(price_max=60000))
    ok = _candidate("Phở bò", "")
    ok.pricing = PricingCalculation(original_price=60000, discount=0, delivery_fee=16000, final_price=76000)
    over = _candidate("Phở bò", "")
    over.pricing = PricingCalculation(original_price=61000, discount=5000, delivery_fee=0, final_price=56000)
    assert validate_candidate(ok, task).is_valid
    assert not validate_candidate(over, task).is_valid
    # _reasoning uses a 15k delivery fee: final 75k = dish 60k + ship 15k
    text = _reasoning(final_price=75000, task={"hard_constraints": {"price_max": 60000}})
    assert "giá món 60,000đ, trong ngân sách bạn đặt 60,000đ" in text


def test_budget_line_labels_profile_budget_when_no_price_stated():
    text = _reasoning(final_price=55000, pref=UserPreference(user_id="u", budget=80000))
    assert "trong ngân sách trong hồ sơ 80,000đ" in text


def test_ingredient_check_covers_request_excludes_and_admits_missing_data():
    task = {"ingredient_excludes": ["hành"]}
    with_data = _reasoning(task=task)
    assert "🛡️" in with_data and "hành" in with_data

    no_data = _reasoning(dish=Dish(id="d2", restaurant_id="r1", name="Bún bò", price=40000), task=task)
    assert "🛡️" not in no_data
    assert "chưa kiểm tra được: hành" in no_data


def test_distance_line_does_not_claim_expansion_when_not_expanded():
    far = Restaurant(id="r1", name="Quán", cuisine="Vietnamese", rating=4.5, distance_km=7.0, delivery_fee=15000)
    assert "mở rộng" not in _reasoning(rest=far, is_radius_expanded=False)
    assert "mở rộng bán kính lên 10km" in _reasoning(rest=far, is_radius_expanded=True, search_radius_km=10.0)


def test_semantic_reason_has_no_invented_taste_claims():
    dish = Dish(id="d1", restaurant_id="r1", name="Phở bò", price=40000, description="Phở truyền thống")
    text = _reasoning(dish=dish, task={"semantic_attributes": [{"text": "đồ nước"}]})
    assert "Hợp ý \"đồ nước\"" in text
    assert "nóng hổi" not in text and "đậm đà" not in text


def test_format_header_uses_actual_radius():
    c = _candidate("Bún bò", "")
    out = format_recommendations_output([c], is_radius_expanded=True, user_address="Q", search_radius_km=8.0)
    assert "8km" in out and "10km" not in out


# ---------------------------------------------------------------------------
# 4. RESPOND: LLM wording must not alter verified facts; chit-chat answers current input
# ---------------------------------------------------------------------------

def _agent_with_reply(reply: str) -> FoodAgent:
    agent = FoodAgent(user_id="user_01", force_mock=True)
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.content = reply
    agent.client = client
    return agent


def test_numbers_normalises_separators():
    assert _numbers("Giá 55,000đ, 4.8⭐, 1.5km") == _numbers("55.000 | 4.8 | 1.5")


def test_llm_reply_with_invented_number_falls_back_to_structured_output():
    structured = "**1. Bún bò — Quán**\n- 💵 Giá: **55,000đ**\n- ⭐ 4.5⭐"
    assert _agent_with_reply("Bún bò chỉ 45,000đ thôi!")._generate_llm_reply(structured) == structured


def test_llm_reply_with_only_verified_numbers_is_kept():
    structured = "**1. Bún bò — Quán**\n- 💵 Giá: **55,000đ**\n- ⭐ 4.5⭐"
    reply = "Gợi ý số 1: Bún bò ở Quán, giá 55.000đ, rating 4.5⭐."
    assert _agent_with_reply(reply)._generate_llm_reply(structured) == reply


def test_chit_chat_replies_to_current_message_not_previous_turn():
    agent = _agent_with_reply("Chào bạn!")
    agent.messages.append({"role": "assistant", "content": "câu trả lời lượt trước"})
    agent.run("xin chào")
    sent = agent.client.chat.completions.create.call_args.kwargs["messages"]
    assert sent[-1]["content"] == "xin chào"
