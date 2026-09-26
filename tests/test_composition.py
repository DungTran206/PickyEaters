# -*- coding: utf-8 -*-
"""
#8 Multi-object orders:
- one distinct dish per requested object (two Mains give two dishes);
- objects without a concept are filled by role (e.g. any drink);
- same_restaurant is only required when stated; same_order prefers one restaurant and
  splits across restaurants (one delivery fee each) when none has everything;
- several combos per restaurant are produced so VALIDATE/RANK pick, not "cheapest first";
- missing items are reported as structured evidence for RE-PLAN.
"""

from agent.composer import compose_candidates, unavailable_objects
from agent.planner import composition_mode
from agent.replan import diagnose_and_replan
from agent.task_model import HardConstraints, Relationship, TaskModel, TaskObject
from agent.validator import validate_candidates_list
from database.models import Dish, Restaurant
from services.recommendation import format_recommendations_output


def _rest(rid, dist=2.0, fee=15000):
    return Restaurant(id=rid, name=f"Quán {rid}", cuisine="Vietnamese", rating=4.5, distance_km=dist, delivery_fee=fee)


def _dish(did, rid, name, price, category="Main"):
    return Dish(id=did, restaurant_id=rid, name=name, price=price, category=category)


def _task(*objects, rel=None, **kw):
    rels = [Relationship(type=rel, objects=list(range(len(objects))))] if rel else []
    return TaskModel(intent="request_recommendation", objects=list(objects), relationships=rels, **kw)


PHO = TaskObject(role="Main", concept="phở")
BUN_CHA = TaskObject(role="Main", concept="bún chả")
ANY_DRINK = TaskObject(role="Drink", concept=None)


def test_composition_mode_is_never_inferred_as_same_restaurant():
    assert composition_mode(_task(PHO)) == "single"
    assert composition_mode(_task(PHO, ANY_DRINK)) == "same_order"
    assert composition_mode(_task(PHO, ANY_DRINK, rel="same_order")) == "same_order"
    assert composition_mode(_task(PHO, ANY_DRINK, rel="same_restaurant")) == "same_restaurant"


def test_two_mains_give_two_dishes():
    dishes = [_dish("p", "r1", "Phở bò", 50000), _dish("b", "r1", "Bún chả Hà Nội", 45000)]
    [c] = compose_candidates(_task(PHO, BUN_CHA, rel="same_order"), dishes, restaurants=[_rest("r1")])
    assert [i.id for i in c.items] == ["p", "b"]
    assert c.pricing.original_price == 95000


def test_slot_without_concept_is_filled_by_role():
    dishes = [_dish("p", "r1", "Phở bò", 50000), _dish("t", "r1", "Trà đào", 20000, category="Drink")]
    [c] = compose_candidates(_task(PHO, ANY_DRINK), dishes, restaurants=[_rest("r1")])
    assert [i.id for i in c.items] == ["p", "t"]


def test_same_order_splits_across_restaurants_with_one_fee_each():
    dishes = [_dish("p", "r1", "Phở bò", 50000), _dish("t", "r2", "Trà đào", 20000, category="Drink")]
    rests = [_rest("r1", dist=2.0, fee=15000), _rest("r2", dist=4.0, fee=12000)]
    [c] = compose_candidates(_task(PHO, ANY_DRINK, rel="same_order"), dishes, restaurants=rests)
    assert {r.id for r in c.restaurants} == {"r1", "r2"}
    assert c.pricing.delivery_fee == 27000
    assert c.pricing.final_price == 50000 + 20000 + 27000
    assert c.restaurant.id == "r2"          # farthest restaurant bounds the delivery
    text = format_recommendations_output([c])
    assert "Tách đơn 2 quán" in text and "2 lần phí ship" in text


def test_same_restaurant_never_splits():
    dishes = [_dish("p", "r1", "Phở bò", 50000), _dish("t", "r2", "Trà đào", 20000, category="Drink")]
    task = _task(PHO, ANY_DRINK, rel="same_restaurant")
    assert compose_candidates(task, dishes, restaurants=[_rest("r1"), _rest("r2")]) == []


def test_single_restaurant_preferred_over_split():
    dishes = [
        _dish("p1", "r1", "Phở bò", 50000), _dish("t1", "r1", "Trà đào", 20000, category="Drink"),
        _dish("t2", "r2", "Trà tắc", 10000, category="Drink"),
    ]
    candidates = compose_candidates(_task(PHO, ANY_DRINK), dishes, restaurants=[_rest("r1"), _rest("r2")])
    assert candidates and all(not c.restaurants for c in candidates)


def test_several_combos_let_validation_pick_one_within_budget():
    # The cheapest main is fine, but the old composer only tried one fixed pairing per restaurant.
    dishes = [
        _dish("p_exp", "r1", "Phở bò đặc biệt", 90000), _dish("p_std", "r1", "Phở bò", 40000),
        _dish("t", "r1", "Trà đào", 15000, category="Drink"),
    ]
    task = _task(PHO, ANY_DRINK, rel="same_restaurant", hard_constraints=HardConstraints(price_max=60000))
    candidates = compose_candidates(task, dishes, restaurants=[_rest("r1")])
    valid, rejected = validate_candidates_list(candidates, task)
    assert [[i.id for i in c.items] for c in valid] == [["p_std", "t"]]
    assert rejected and rejected[0][1][0].constraint_type == "price_max"


def test_unavailable_item_is_reported_to_replan():
    dishes = [_dish("p", "r1", "Phở bò", 50000)]
    task = _task(PHO, TaskObject(role="Drink", concept="trà chanh"), rel="same_order")
    assert unavailable_objects(task, dishes) == ["trà chanh"]
    action = diagnose_and_replan(task, [], current_radius_km=10.0, is_radius_expanded=True,
                                 dishes_retrieved_count=1, unavailable_objects=["trà chanh"])
    assert action.diagnosis == "requested_item_unavailable"
    assert "'trà chanh'" in action.message_to_user and "'phở'" in action.message_to_user


def test_party_size_multiplies_every_item_in_split_orders():
    dishes = [_dish("p", "r1", "Phở bò", 50000), _dish("t", "r2", "Trà đào", 20000, category="Drink")]
    task = _task(PHO, ANY_DRINK, context={"party_size": 2})
    [c] = compose_candidates(task, dishes, restaurants=[_rest("r1"), _rest("r2")])
    assert c.pricing.original_price == 2 * 70000
