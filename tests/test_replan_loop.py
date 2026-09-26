# -*- coding: utf-8 -*-
"""
#7 RE-PLAN is a bounded strategy loop driven by observations:
- radius widens along a schedule derived from the plan (not a fixed 5 -> 10 km);
- then the SOFT cuisine preference may be dropped, only if something else describes the food;
- hard constraints are never relaxed; every attempt is traced.
"""

import agent.executor as executor
from agent.executor import execute_recommendation
from agent.replan import (
    MAX_REPLAN_STEPS,
    MIN_OPTIONS,
    SearchState,
    apply_step,
    next_step,
    radius_schedule,
)
from agent.task_model import HardConstraints, TaskModel, TaskObject
from database.models import Dish, Restaurant, UserPreference


def test_radius_schedule_comes_from_the_plan():
    assert radius_schedule(5, 10) == [5, 10]
    assert radius_schedule(3, 10) == [3, 6, 10]
    assert radius_schedule(10, 10) == [10]
    assert radius_schedule(0, 10) == [10]   # never loops forever


def _state(**kw):
    base = dict(radius_km=3.0, radii=[3.0, 6.0, 10.0])
    base.update(kw)
    return SearchState(**base)


def test_enough_options_stops():
    assert next_step(_state(), MIN_OPTIONS) is None


def test_widens_radius_step_by_step_then_relaxes_soft_cuisine_then_stops():
    state = _state(cuisine="Japanese", cuisine_relaxable=True)
    actions = []
    while (step := next_step(state, 0)) is not None:
        actions.append((step.action, step.radius_km))
        state.trace.append({})
        state = apply_step(state, step)
    assert actions == [("expand_radius", 6.0), ("expand_radius", 10.0), ("relax_cuisine", None)]
    assert state.active_cuisine is None and state.relaxed == ["cuisine"]


def test_cuisine_that_is_the_whole_request_is_not_relaxed():
    state = _state(radius_km=10.0, radii=[10.0], cuisine="Japanese", cuisine_relaxable=False)
    assert next_step(state, 0) is None


def test_step_bound():
    state = _state(radii=[1.0 * i for i in range(1, 20)], radius_km=1.0)
    state.trace.extend({} for _ in range(MAX_REPLAN_STEPS))
    assert next_step(state, 0) is None


def test_too_few_options_also_widens():
    step = next_step(_state(), 1)
    assert step.action == "expand_radius" and step.reason == "too_few_options"


# ---------------------------------------------------------------------------
# Executor loop against a controlled search
# ---------------------------------------------------------------------------

def _near_and_far():
    near = Restaurant(id="rn", name="Gần", cuisine="Vietnamese", rating=4.5, distance_km=2.0, delivery_fee=15000)
    far = Restaurant(id="rf", name="Xa", cuisine="Vietnamese", rating=4.5, distance_km=8.0, delivery_fee=15000)
    dishes = {
        "rn": [Dish(id="n1", restaurant_id="rn", name="Phở bò", price=80000)],
        "rf": [Dish(id="f1", restaurant_id="rf", name="Phở bò", price=40000),
               Dish(id="f2", restaurant_id="rf", name="Phở gà", price=45000)],
    }
    return [near, far], dishes


def _fake_search(radii_seen):
    rests, dishes = _near_and_far()

    def search(radius_km, **_):
        radii_seen.append(radius_km)
        in_range = [r for r in rests if r.distance_km <= radius_km]
        return {
            "dishes": [d for r in in_range for d in dishes[r.id]],
            "restaurants": in_range,
            "search_radius_km": radius_km,
        }
    return search


def test_loop_widens_until_enough_valid_options_and_never_relaxes_budget(monkeypatch):
    radii = []
    monkeypatch.setattr(executor, "search_within_radius", _fake_search(radii))
    task = TaskModel(
        intent="request_recommendation",
        objects=[TaskObject(role="Main", concept="phở")],
        hard_constraints=HardConstraints(price_max=50000),
    )
    result = execute_recommendation(
        task_obj=task, task_model=task.model_dump(mode="json"), pref=UserPreference(user_id="u"),
        user_address="Cầu Giấy, Hà Nội", keyword="phở", initial_radius=3.0, max_radius=10.0,
    )
    # 3km and 6km: only the near 80k dish (over budget); 10km: two valid dishes.
    assert radii == [3.0, 6.0, 10.0]
    assert [t["valid"] for t in result["replan_trace"]] == [0, 0, 2]
    assert result["is_radius_expanded"] is True
    ids = {c.dish.id for c in result["candidates"]}
    assert ids == {"f1", "f2"}                       # the over-budget 80k dish never appears
    assert all(c.pricing.original_price <= 50000 for c in result["candidates"])


def test_loop_reports_budget_diagnosis_when_budget_is_the_blocker(monkeypatch):
    monkeypatch.setattr(executor, "search_within_radius", _fake_search([]))
    task = TaskModel(
        intent="request_recommendation",
        objects=[TaskObject(role="Main", concept="phở")],
        hard_constraints=HardConstraints(price_max=30000),
    )
    result = execute_recommendation(
        task_obj=task, task_model=task.model_dump(mode="json"), pref=UserPreference(user_id="u"),
        user_address="Cầu Giấy, Hà Nội", keyword="phở", initial_radius=5.0, max_radius=10.0,
    )
    assert result["candidates"] == []
    assert result["replan_action"].diagnosis == "budget_too_tight"
    assert result["replan_action"].suggested_budget == 40000
