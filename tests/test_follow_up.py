# -*- coding: utf-8 -*-
"""
Follow-up, conversation reference and party size — contract tests.

- PLAN merges a follow-up with the previous effective task (session state), and
  derives request-scoped constraints: cheaper-than-reference, not-shown-before.
- VALIDATE enforces those constraints with structured violations.
- RE-PLAN diagnoses them per candidate.
- ACT/COMPOSE price all portions for context.party_size (one delivery fee).
- provide_info with conversation_ref answers from the referenced candidate's data.
"""

import pytest

from agent.agent import FoodAgent
from agent.composer import compose_candidates
from agent.planner import follow_up_constraints, merge_follow_up, plan_recommendation
from agent.replan import diagnose_and_replan
from agent.task_model import (
    FollowUp, HardConstraints, Relationship, TaskContext, TaskModel, TaskObject,
)
from agent.validator import ConstraintViolation, validate_candidate
from database.db import reset_database
from database.models import Dish, PricingCalculation, RecommendationCandidate, Restaurant
from services.recommendation import rank_candidates


def _prev_task(**kw) -> TaskModel:
    return TaskModel(
        intent="request_recommendation",
        objects=[TaskObject(role="Main", concept="phở")],
        excluded_concepts=["cơm"],
        context=TaskContext(party_size=2),
        **kw,
    )


def _prev_candidate(dish_id: str, final_price: int) -> dict:
    return {
        "dish": {"id": dish_id, "name": dish_id},
        "items": [{"id": dish_id, "name": dish_id}],
        "pricing": {"final_price": final_price},
    }


# ---------------------------------------------------------------------------
# PLAN: merge + constraints
# ---------------------------------------------------------------------------

class TestMergeFollowUp:
    def test_refine_without_objects_carries_previous_request(self):
        current = TaskModel(intent="request_recommendation",
                            follow_up=FollowUp(type="refine", reason="lower_price"))
        merged = merge_follow_up(current, _prev_task())
        assert [o.concept for o in merged.objects] == ["phở"]
        assert merged.excluded_concepts == ["cơm"]
        assert merged.context.party_size == 2
        assert merged.follow_up.type == "refine"

    def test_new_request_does_not_carry_previous(self):
        current = TaskModel(intent="request_recommendation",
                            objects=[TaskObject(role="Main", concept="bún")],
                            follow_up=FollowUp(type="new_request"))
        assert merge_follow_up(current, _prev_task()) is current

    def test_no_follow_up_does_not_carry_previous(self):
        current = TaskModel(intent="request_recommendation")
        assert merge_follow_up(current, _prev_task()) is current

    def test_current_values_override_and_exclusions_accumulate(self):
        prev = _prev_task(hard_constraints=HardConstraints(price_min=50000))
        current = TaskModel(
            intent="request_recommendation",
            objects=[TaskObject(role="Main", concept="bún"), TaskObject(role="Drink", concept="trà")],
            relationships=[Relationship(type="same_order", objects=[0, 1])],
            hard_constraints=HardConstraints(price_max=40000),
            excluded_concepts=["gà"],
            follow_up=FollowUp(type="reject_previous"),
        )
        merged = merge_follow_up(current, prev)
        assert [o.concept for o in merged.objects] == ["bún", "trà"]
        assert merged.relationships[0].objects == [0, 1]
        # Price bounds are taken as a pair from the current turn (no min > max conflict).
        assert (merged.hard_constraints.price_min, merged.hard_constraints.price_max) == (None, 40000)
        assert merged.excluded_concepts == ["cơm", "gà"]


class TestFollowUpConstraints:
    previous = [_prev_candidate("a", 70000), _prev_candidate("b", 50000)]

    def test_lower_price_is_relative_to_first_shown_option(self):
        task = TaskModel(intent="request_recommendation", follow_up=FollowUp(type="refine", reason="lower_price"))
        assert follow_up_constraints(task, self.previous) == {"max_final_price": 69999}

    def test_conversation_ref_selects_the_reference_option(self):
        task = TaskModel(intent="request_recommendation",
                         follow_up=FollowUp(type="refine", reason="lower_price"),
                         context=TaskContext(conversation_ref="2"))
        assert follow_up_constraints(task, self.previous)["max_final_price"] == 49999

    def test_reject_previous_excludes_everything_shown_in_the_chain(self):
        task = TaskModel(intent="request_recommendation", follow_up=FollowUp(type="reject_previous"))
        out = follow_up_constraints(task, self.previous, shown_dish_ids=["z", "a"])
        assert out == {"exclude_dish_ids": ["z", "a", "b"]}

    def test_too_expensive_rejects_and_requires_cheaper(self):
        task = TaskModel(intent="request_recommendation",
                         follow_up=FollowUp(type="reject_previous", reason="too_expensive"))
        out = follow_up_constraints(task, self.previous)
        assert out["max_final_price"] == 69999 and out["exclude_dish_ids"] == ["a", "b"]

    @pytest.mark.parametrize("follow_up", [None, FollowUp(type="new_request")])
    def test_no_constraints_without_a_follow_up(self, follow_up):
        task = TaskModel(intent="request_recommendation", follow_up=follow_up)
        assert follow_up_constraints(task, self.previous) == {}

    def test_plan_returns_merged_task_and_constraints(self):
        current = TaskModel(intent="request_recommendation",
                            follow_up=FollowUp(type="refine", reason="lower_price"))
        plan = plan_recommendation(current, "u1", previous_task=_prev_task(), previous_candidates=self.previous)
        assert plan["keyword"] == "phở"
        assert plan["max_final_price"] == 69999
        assert plan["task_model"]["context"]["party_size"] == 2


# ---------------------------------------------------------------------------
# VALIDATE + RE-PLAN
# ---------------------------------------------------------------------------

def _cand(dish_id="d1", final_price=60000, price=45000) -> RecommendationCandidate:
    dish = Dish(id=dish_id, restaurant_id="r1", name="Phở bò", price=price, ingredients=["bò"])
    rest = Restaurant(id="r1", name="Quán", cuisine="Vietnamese", rating=4.5, distance_km=1.0, delivery_fee=15000)
    pricing = PricingCalculation(original_price=final_price - 15000, discount=0,
                                 delivery_fee=15000, final_price=final_price)
    return RecommendationCandidate(dish=dish, restaurant=rest, pricing=pricing, items=[dish])


def test_validator_enforces_follow_up_constraints():
    task = TaskModel(intent="request_recommendation")
    res = validate_candidate(_cand(final_price=60000), task, max_final_price=59999, exclude_dish_ids=["d1"])
    assert {v.constraint_type for v in res.violations} == {"follow_up_max_price", "previously_shown"}
    assert validate_candidate(_cand(final_price=59999), task, max_final_price=59999).is_valid


def test_replan_reports_no_cheaper_option():
    task = TaskModel(intent="request_recommendation", objects=[TaskObject(role="Main", concept="phở")])
    v = ConstraintViolation(constraint_type="follow_up_max_price", field="price", message="",
                            actual_value=60000, expected_value=49999)
    action = diagnose_and_replan(task, [(_cand(final_price=60000), [v])], dishes_retrieved_count=1)
    assert action.diagnosis == "no_cheaper_option"
    assert "50,000đ" in action.message_to_user and "60,000đ" in action.message_to_user


def test_replan_ingredient_diagnosis_counts_candidates_not_violations():
    # A combo with two excluded ingredients + a candidate that is only spicy:
    # 2 ingredient violations == 2 rejected candidates, but not every candidate has one.
    task = TaskModel(intent="request_recommendation", ingredient_excludes=["hành"])
    ing = ConstraintViolation(constraint_type="ingredient_exclude", field="ingredients", message="")
    spicy = ConstraintViolation(constraint_type="spicy", field="spicy", message="")
    rejected = [(_cand("a"), [ing, ing]), (_cand("b"), [spicy])]
    assert diagnose_and_replan(task, rejected, dishes_retrieved_count=2).diagnosis != "ingredient_conflict"


# ---------------------------------------------------------------------------
# party_size pricing
# ---------------------------------------------------------------------------

def test_rank_prices_all_portions_with_one_delivery_fee():
    rest = Restaurant(id="rx", name="Quán", cuisine="Vietnamese", rating=4.5, distance_km=1.0, delivery_fee=15000)
    dish = Dish(id="dx", restaurant_id="rx", name="Phở bò", price=50000)
    [c] = rank_candidates([dish], restaurants=[rest], quantity=2, top_k=None)
    assert c.quantity == 2
    assert c.pricing.original_price == 100000
    assert c.pricing.final_price == 115000


def test_composer_prices_all_portions():
    rest = Restaurant(id="rx", name="Quán", cuisine="Vietnamese", rating=4.5, distance_km=1.0, delivery_fee=15000)
    dishes = [Dish(id="m", restaurant_id="rx", name="Phở bò", price=50000),
              Dish(id="t", restaurant_id="rx", name="Trà chanh", price=10000, category="Drink")]
    task = TaskModel(
        intent="request_recommendation",
        objects=[TaskObject(role="Main", concept="phở"), TaskObject(role="Drink", concept="trà chanh")],
        relationships=[Relationship(type="same_order", objects=[0, 1])],
        context=TaskContext(party_size=3),
    )
    [c] = compose_candidates(task, dishes, restaurants=[rest])
    assert c.quantity == 3
    assert c.pricing.original_price == 180000


# ---------------------------------------------------------------------------
# End-to-end through the agent (regex Understand path)
# ---------------------------------------------------------------------------

@pytest.fixture
def agent():
    reset_database()
    return FoodAgent(user_id="user_01", force_mock=True)


def test_cheaper_follow_up_only_returns_cheaper_options(agent):
    first = agent.run("muốn ăn phở")
    reference = first["candidates"][0]["pricing"]["final_price"]
    cheaper = agent.run("rẻ hơn đi")
    assert cheaper["candidates"]
    assert all(c["pricing"]["final_price"] < reference for c in cheaper["candidates"])
    assert all("phở" in c["dish"]["name"].lower() for c in cheaper["candidates"])


def test_reject_follow_up_never_repeats_shown_dishes(agent):
    shown = set()
    for text in ("muốn ăn phở", "rẻ hơn đi"):
        shown |= {c["dish"]["id"] for c in agent.run(text)["candidates"]}
    other = agent.run("món khác đi")
    assert other["candidates"]
    assert not shown & {c["dish"]["id"] for c in other["candidates"]}


def test_info_question_about_referenced_option_uses_its_data(agent):
    shown = agent.run("muốn ăn phở")["candidates"]
    answer = agent.run("món số 2 mở đến mấy giờ")["response"]
    second = shown[1]
    assert second["dish"]["name"] in answer
    assert f"{second['pricing']['final_price']:,}đ" in answer
    if second["restaurant"]["open_hours"]:
        assert second["restaurant"]["open_hours"] in answer


def test_failed_follow_up_keeps_previous_options_for_reference(agent):
    shown = agent.run("muốn ăn phở")["candidates"]
    agent.last_candidates = [dict(c, pricing=dict(c["pricing"], final_price=1)) for c in shown]
    none_cheaper = agent.run("rẻ hơn đi")
    assert none_cheaper["candidates"] == []
    assert "rẻ hơn" in none_cheaper["response"]
    assert agent.last_candidates  # still available for "món số N"
