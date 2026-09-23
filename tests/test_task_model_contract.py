import pytest
from pydantic import ValidationError

from agent.planner import plan_recommendation
from agent.task_model import TaskModel
from agent.understand import understand


def test_broth_food_is_main_semantic_attribute_not_drink():
    task = understand("t muốn đồ nước")
    assert task.intent == "request_recommendation"
    assert [obj.role for obj in task.objects] == ["Main"]
    assert task.objects[0].concept is None
    assert task.semantic_attributes[0].text == "đồ nước"


def test_negated_food_does_not_become_requested_object():
    task = understand("không muốn ăn cơm")
    assert task.intent == "request_recommendation"
    assert task.objects == []
    assert task.excluded_concepts == ["cơm"]


def test_negation_does_not_hide_another_positive_order_object():
    task = understand("không muốn ăn cơm, muốn trà chanh")
    assert task.excluded_concepts == ["cơm"]
    assert [(obj.role, obj.concept) for obj in task.objects] == [("Drink", "trà chanh")]


def test_composed_order_preserves_price_range_and_roles():
    task = understand("40-80k muốn cơm với trà chanh")
    assert [(obj.role, obj.concept) for obj in task.objects] == [
        ("Main", "cơm"), ("Drink", "trà chanh")
    ]
    assert task.hard_constraints.price_min == 40000
    assert task.hard_constraints.price_max == 80000
    assert task.relationships[0].type == "same_order"
    assert task.relationships[0].objects == [0, 1]


def test_party_size_does_not_change_total_budget():
    task = understand("2 người dưới 150k, không cay")
    assert task.context.party_size == 2
    assert task.hard_constraints.price_max == 150000
    assert task.hard_constraints.spicy is False


def test_open_qualitative_attribute_and_no_profile_copy():
    task = understand("tối nay ăn gì nhẹ nhẹ?")
    assert task.objects == []
    assert task.semantic_attributes[0].text == "nhẹ nhẹ"
    plan = plan_recommendation(task, "u1", profile={"budget": 50000, "preferred_cuisines": ["Korean"]})
    assert plan["max_price"] is None
    assert plan["cuisine"] == "Korean"


def test_follow_up_reference_must_match_supplied_ordinal():
    task = understand(
        "món số 2 đắt quá, tìm cái khác",
        [{"ordinal": "1", "name": "Món A"}, {"ordinal": "2", "name": "Món B"}],
    )
    assert task.follow_up.type == "reject_previous"
    assert task.follow_up.reason == "too_expensive"
    assert task.context.conversation_ref == "2"

    ambiguous = understand("cái này", [{"ordinal": "1"}, {"ordinal": "2"}])
    assert ambiguous.context.conversation_ref is None


def test_ingredient_exclusion_is_separate_from_concept_exclusion():
    task = understand("tao ghét hành")
    assert task.intent == "state_preference"
    assert task.ingredient_excludes == ["hành"]
    assert task.excluded_concepts == []


def test_bare_food_name_is_a_recommendation_request():
    task = understand("xôi")
    assert task.intent == "request_recommendation"
    assert [(obj.role, obj.concept) for obj in task.objects] == [("Main", "xôi")]


def test_task_model_rejects_invalid_relationship_indices_and_price_range():
    with pytest.raises(ValidationError):
        TaskModel.model_validate({
            "intent": "request_recommendation",
            "objects": [{"role": "Main", "concept": "cơm"}],
            "relationships": [{"type": "same_order", "objects": [0, 1]}],
        })
    with pytest.raises(ValidationError):
        TaskModel.model_validate({
            "intent": "request_recommendation",
            "hard_constraints": {"price_min": 90000, "price_max": 50000},
        })
