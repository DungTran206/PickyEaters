import pytest

from agent.agent import FoodAgent
from database.db import get_user_preferences, reset_database


@pytest.fixture(autouse=True)
def setup_db():
    reset_database()
    yield


def recommendation_call(result):
    return next(call for call in result["tool_calls"] if call["tool"] == "recommend_dishes_with_radius")


def test_agent_passes_explicit_spice_and_budget_from_task_model():
    result = FoodAgent(user_id="user_01", force_mock=True).run("Món cay dưới 80k")
    task = result["task_model"]
    assert task["intent"] == "request_recommendation"
    assert task["hard_constraints"]["spicy"] is True
    assert task["hard_constraints"]["price_max"] == 80000
    args = recommendation_call(result)["arguments"]
    assert args["spicy"] is True
    assert args["max_price"] == 80000


def test_agent_passes_explicit_cuisine_without_raw_request():
    result = FoodAgent(user_id="user_01", force_mock=True).run("Đồ Hàn gần đây")
    task = result["task_model"]
    assert task["soft_preferences"]["cuisine_affinity"] == ["Korean"]
    args = recommendation_call(result)["arguments"]
    assert args["cuisine"] == "Korean"
    assert "current_request" not in args


def test_agent_preserves_single_budget_bound():
    result = FoodAgent(user_id="user_01", force_mock=True).run("Tao muốn ăn nhưng không quá 60k")
    assert recommendation_call(result)["arguments"]["max_price"] == 60000


def test_promotion_priority_is_structured():
    result = FoodAgent(user_id="user_01", force_mock=True).run("Có món nào đang sale không?")
    assert result["task_model"]["soft_preferences"]["priority_order"] == ["promotion"]


def test_state_preference_updates_durable_profile_and_is_used_later():
    agent = FoodAgent(user_id="user_01", force_mock=True)
    result = agent.run("Tao không thích hành")
    assert result["task_model"]["intent"] == "state_preference"
    assert result["task_model"]["ingredient_excludes"] == ["hành"]
    assert "hành" in get_user_preferences("user_01").disliked_ingredients

    next_result = agent.run("Tối nay ăn gì?")
    assert "hành" in recommendation_call(next_result)["arguments"]["disliked_ingredients"]


def test_underspecified_recommendation_still_returns_a_valid_task_model():
    result = FoodAgent(user_id="user_01", force_mock=True).run("Tối nay ăn gì?")
    assert result["task_model"]["intent"] == "request_recommendation"
    assert result["task_model"]["objects"] == []
    assert recommendation_call(result)


def test_party_budget_is_not_divided_in_understand_or_plan():
    result = FoodAgent(user_id="user_01", force_mock=True).run("Tìm đồ ăn cho 2 người dưới 150k")
    task = result["task_model"]
    assert task["context"]["party_size"] == 2
    assert task["hard_constraints"]["price_max"] == 150000
    assert recommendation_call(result)["arguments"]["max_price"] == 150000


def test_specific_food_concept_is_structured_before_search():
    result = FoodAgent(user_id="user_01", force_mock=True).run("Muốn ăn món giống bún bò")
    assert result["task_model"]["objects"][0]["concept"] == "bún bò"
    assert recommendation_call(result)["arguments"]["keyword"] == "bún bò"


def test_follow_up_bare_food_name_does_not_fall_back_to_chit_chat():
    agent = FoodAgent(user_id="user_01", force_mock=True)
    agent.run("Tối nay ăn gì?")

    result = agent.run("xôi")

    assert result["task_model"]["intent"] == "request_recommendation"
    assert result["task_model"]["objects"][0]["concept"] == "xôi"
    assert recommendation_call(result)["arguments"]["keyword"] == "xôi"
    assert "Tao đây" not in result["response"]


def test_rank_priority_comes_from_task_model():
    result = FoodAgent(user_id="user_01", force_mock=True).run("Tao muốn món rating cao nhưng đừng quá đắt")
    assert result["task_model"]["soft_preferences"]["priority_order"] == ["rating", "price"]
