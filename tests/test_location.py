# -*- coding: utf-8 -*-
"""
Delivery location: no default address anywhere. The user types an address (with a district)
or picks a point on the map; without one, PLAN asks instead of assuming a location.
"""

import pytest
from fastapi.testclient import TestClient

from agent.agent import FoodAgent
from api import app
from database.db import get_user_preferences, reset_database, set_user_location, update_user_preference
from database.models import UserPreference
from services.search import (
    MIN_ESTIMATED_KM,
    district_label,
    estimate_distance,
    nearest_district,
)

THANH_XUAN_POINT = (20.9950, 105.8105)   # a point inside Thanh Xuân, near its centre
DA_NANG_POINT = (16.0544, 108.2022)      # outside the covered districts


@pytest.fixture(autouse=True)
def fresh_db():
    reset_database()


def test_new_profile_has_no_address():
    pref = UserPreference(user_id="x")
    assert (pref.address, pref.district, pref.latitude, pref.longitude) == ("", "", None, None)
    stored = get_user_preferences("brand_new_user")
    assert stored.address == "" and stored.latitude is None


def test_agent_asks_for_location_instead_of_assuming_one():
    result = FoodAgent(user_id="user_new", force_mock=True).run("muốn ăn phở")
    assert result["candidates"] == []
    assert "bản đồ" in result["response"]
    assert not [c for c in result["tool_calls"] if c["tool"] == "recommend_dishes_with_radius"]


# ---------------------------------------------------------------------------
# Map point → district label and distances
# ---------------------------------------------------------------------------

def test_nearest_district_labels_a_map_point():
    assert nearest_district(*THANH_XUAN_POINT) == "thanh xuan"
    assert district_label(None, THANH_XUAN_POINT) == "Thanh Xuân, Hà Nội"
    assert nearest_district(*DA_NANG_POINT) is None


def test_distance_from_map_point_uses_the_point():
    km, basis = estimate_distance("", "12 Nguyễn Trãi, Thanh Xuân, Hà Nội", THANH_XUAN_POINT)
    assert basis == "district_centroid" and MIN_ESTIMATED_KM <= km < 1.0
    far_km, _ = estimate_distance("", "Cầu Giấy, Hà Nội", THANH_XUAN_POINT)
    assert far_km > km


def test_agent_recommends_from_a_map_point_and_saves_it():
    result = FoodAgent(user_id="user_new", force_mock=True).run(
        "muốn ăn phở", user_lat=THANH_XUAN_POINT[0], user_lng=THANH_XUAN_POINT[1]
    )
    assert result["candidates"]
    assert all(c["restaurant"]["distance_basis"] == "district_centroid" for c in result["candidates"])
    pref = get_user_preferences("user_new")
    assert (pref.latitude, pref.longitude) == THANH_XUAN_POINT
    assert pref.address == "Vị trí trên bản đồ (gần Thanh Xuân, Hà Nội)"


def test_saved_map_point_is_used_on_later_turns():
    agent = FoodAgent(user_id="user_new", force_mock=True)
    agent.run("xin chào", user_lat=THANH_XUAN_POINT[0], user_lng=THANH_XUAN_POINT[1])
    assert agent.run("muốn ăn phở")["candidates"]


def test_unlocatable_address_is_not_saved():
    FoodAgent(user_id="user_new", force_mock=True).run("muốn ăn phở", user_address="Số 5 Kim Mã, Hà Nội")
    assert get_user_preferences("user_new").address == ""


def test_typed_address_replaces_map_pin():
    set_user_location("user_new", "Vị trí trên bản đồ", "Thanh Xuân, Hà Nội", *THANH_XUAN_POINT)
    update_user_preference("user_new", "address", "Quận 3, TP.HCM")
    pref = get_user_preferences("user_new")
    assert pref.address == "Quận 3, TP.HCM" and pref.latitude is None and pref.longitude is None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

client = TestClient(app)


def test_api_saves_map_point():
    res = client.post("/api/user/user_new", json={"latitude": THANH_XUAN_POINT[0], "longitude": THANH_XUAN_POINT[1]})
    assert res.status_code == 200
    body = res.json()
    assert body["latitude"] == THANH_XUAN_POINT[0] and "Thanh Xuân" in body["address"]


def test_api_rejects_unlocatable_address():
    res = client.post("/api/user/user_new", json={"address": "Số 5 Kim Mã, Hà Nội"})
    assert res.status_code == 400
    assert get_user_preferences("user_new").address == ""


def test_api_locate_reports_coverage():
    assert client.get("/api/locate", params={"lat": THANH_XUAN_POINT[0], "lng": THANH_XUAN_POINT[1]}).json() == {
        "district": "Thanh Xuân, Hà Nội", "in_coverage": True,
    }
    assert client.get("/api/locate", params={"lat": DA_NANG_POINT[0], "lng": DA_NANG_POINT[1]}).json()["in_coverage"] is False


def test_chat_api_accepts_coordinates():
    res = client.post("/api/chat", json={
        "message": "muốn ăn phở", "user_id": "user_new",
        "user_lat": THANH_XUAN_POINT[0], "user_lng": THANH_XUAN_POINT[1],
    })
    assert res.status_code == 200 and res.json()["candidates"]
