# -*- coding: utf-8 -*-
"""
Tests for the unified deterministic orchestrator and the fixes from architecture review.
Covers:
  - Orchestrator always routes through PLAN→ACT (not free LLM tool-calling)
  - Profile budget NOT silently becoming a hard filter when user didn't state price
  - OpenAI tool schema fix (get_user_preferences required=[user_id] only)
  - RE-PLAN: expand_radius is auto-executed (not just diagnosed)
  - Understand: _parse_and_validate handles pure JSON and fenced JSON
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from agent.agent import FoodAgent
from agent.understand import _parse_and_validate
from agent.tools import OPENAI_TOOLS, tool_recommend_dishes_with_radius
from database.db import reset_database


@pytest.fixture(autouse=True)
def setup_db():
    reset_database()
    yield


# ─────────────────────────────────────────────────────────────────────────────
# 1. Orchestrator: pipeline is always deterministic
# ─────────────────────────────────────────────────────────────────────────────

class TestUnifiedOrchestrator:
    def test_llm_available_still_goes_through_plan_layer(self):
        """Even with a mock LLM client present, PLAN→ACT must run (not free tool-calling)."""
        mock_client = MagicMock()
        # LLM "reply" for _generate_llm_reply
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Đây là gợi ý của tôi!"
        mock_client.chat.completions.create.return_value = mock_response

        agent = FoodAgent(user_id="user_01", force_mock=True)
        agent.client = mock_client  # Inject fake client

        result = agent.run("Muốn ăn phở bò")

        # PLAN must have produced a recommend_dishes_with_radius call
        rec_calls = [c for c in result["tool_calls"] if c["tool"] == "recommend_dishes_with_radius"]
        assert len(rec_calls) == 1, "Pipeline should always call recommend_dishes_with_radius via PLAN"

        # The tool should have keyword set by PLAN, not by LLM
        assert rec_calls[0]["arguments"]["keyword"] == "phở bò"

    def test_no_free_llm_tool_calling(self):
        """The orchestrator must NOT rely on tool_choice='auto' to route tasks."""
        agent = FoodAgent(user_id="user_01", force_mock=True)
        result = agent.run("Tìm gì đó ăn nhẹ")
        # All tool calls should be deterministic; recommend_dishes_with_radius must appear once
        rec_calls = [c for c in result["tool_calls"] if c["tool"] == "recommend_dishes_with_radius"]
        assert len(rec_calls) == 1

    def test_chit_chat_does_not_call_recommend_tool(self):
        """chit_chat intent must be blocked from calling search tools."""
        agent = FoodAgent(user_id="user_01", force_mock=True)
        result = agent.run("Hôm nay trời đẹp nhỉ")
        rec_calls = [c for c in result["tool_calls"] if c["tool"] == "recommend_dishes_with_radius"]
        assert len(rec_calls) == 0, "chit_chat should NOT trigger recommend_dishes_with_radius"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Profile budget separation: soft preference ≠ hard filter
# ─────────────────────────────────────────────────────────────────────────────

class TestProfileBudgetSeparation:
    def test_no_stated_price_does_not_inject_profile_budget_as_max_price(self):
        """When user says no price, max_price in tool args must be None (not pref.budget)."""
        agent = FoodAgent(user_id="user_01", force_mock=True)
        result = agent.run("Tìm phở bò ngon đi")
        rec_call = next(c for c in result["tool_calls"] if c["tool"] == "recommend_dishes_with_radius")
        # max_price must not be silently filled from profile budget
        assert rec_call["arguments"].get("max_price") is None, (
            "Profile budget must NOT become a hard filter when user didn't state price"
        )

    def test_stated_price_is_passed_as_max_price(self):
        """When user explicitly states price, max_price must be set correctly."""
        agent = FoodAgent(user_id="user_01", force_mock=True)
        result = agent.run("Phở bò dưới 50k")
        rec_call = next(c for c in result["tool_calls"] if c["tool"] == "recommend_dishes_with_radius")
        assert rec_call["arguments"]["max_price"] == 50000


# ─────────────────────────────────────────────────────────────────────────────
# 3. OpenAI Tool Schema: get_user_preferences required fix
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenAIToolSchema:
    def _get_tool(self, name: str):
        return next((t for t in OPENAI_TOOLS if t["function"]["name"] == name), None)

    def test_get_user_preferences_required_only_has_user_id(self):
        """Bug fix: required must not include 'task_model' which is absent from properties."""
        tool = self._get_tool("get_user_preferences")
        assert tool is not None
        required = tool["function"]["parameters"]["required"]
        assert required == ["user_id"], f"Expected ['user_id'] but got {required}"
        assert "task_model" not in required

    def test_get_user_preferences_properties_match_required(self):
        """All required fields must exist in properties."""
        tool = self._get_tool("get_user_preferences")
        props = set(tool["function"]["parameters"]["properties"].keys())
        required = set(tool["function"]["parameters"]["required"])
        missing = required - props
        assert not missing, f"Required fields missing from properties: {missing}"

    def test_all_tool_required_fields_exist_in_properties(self):
        """Validate all tools have no dangling required fields."""
        for tool_def in OPENAI_TOOLS:
            func = tool_def["function"]
            params = func.get("parameters", {})
            props = set(params.get("properties", {}).keys())
            required = set(params.get("required", []))
            missing = required - props
            assert not missing, (
                f"Tool '{func['name']}' has required fields not in properties: {missing}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Understand: _parse_and_validate handles pure JSON and fenced JSON
# ─────────────────────────────────────────────────────────────────────────────

class TestParseAndValidateStructuredOutput:
    _base = {
        "intent": "request_recommendation",
        "objects": [{"role": "Main", "concept": "phở bò", "required": True}],
        "hard_constraints": {"price_min": None, "price_max": None, "spicy": None},
        "ingredient_excludes": [],
        "soft_preferences": {"cuisine_affinity": [], "priority_order": []},
        "excluded_concepts": [],
        "semantic_attributes": [],
        "relationships": [],
        "follow_up": None,
        "context": {"party_size": 1, "conversation_ref": None},
    }

    def test_pure_json_no_fence(self):
        """response_format=json_object produces pure JSON — must parse directly."""
        raw = json.dumps(self._base)
        result = _parse_and_validate(raw)
        assert result is not None
        assert result.objects[0].concept == "phở bò"

    def test_json_with_markdown_fence(self):
        """Fallback for providers that still wrap in ```json."""
        raw = "```json\n" + json.dumps(self._base) + "\n```"
        result = _parse_and_validate(raw)
        assert result is not None
        assert result.intent == "request_recommendation"

    def test_json_with_leading_explanation_text(self):
        """LLM sometimes adds preamble before the JSON object."""
        raw = "Đây là kết quả phân tích:\n" + json.dumps(self._base)
        result = _parse_and_validate(raw)
        assert result is not None

    def test_invalid_json_returns_none(self):
        result = _parse_and_validate("this is not json at all")
        assert result is None

    def test_pydantic_violation_returns_none(self):
        bad = dict(self._base)
        bad["intent"] = "invalid_intent_value"
        result = _parse_and_validate(json.dumps(bad))
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. RE-PLAN: expand_radius is executed, not just diagnosed
# ─────────────────────────────────────────────────────────────────────────────

class TestReplanExpandRadiusExecution:
    def test_tool_returns_valid_structure_always(self):
        """
        Sanity check: tool_recommend_dishes_with_radius always returns a valid dict
        regardless of whether RE-PLAN fired.
        """
        result = tool_recommend_dishes_with_radius(
            user_id="user_01",
            keyword="phở",
        )
        assert "status" in result
        assert "candidates" in result
        assert "search_radius_km" in result
        for c in result["candidates"]:
            assert "dish" in c
            assert "restaurant" in c
            assert "pricing" in c

    def test_expand_radius_auto_executed_when_nothing_found(self):
        """
        When the first radius yields nothing, RE-PLAN must execute a wider search itself
        (bounded loop), not just diagnose.
        """
        import agent.executor as executor_module
        original_search = executor_module.search_within_radius
        radii = []

        def recording_search(radius_km, **kwargs):
            radii.append(radius_km)
            if len(radii) == 1:
                return {"dishes": [], "restaurants": [], "search_radius_km": radius_km}
            return original_search(radius_km=radius_km, **kwargs)

        valid_task_model = {
            "intent": "request_recommendation",
            "objects": [{"role": "Main", "concept": "phở", "required": True}],
            "hard_constraints": {"price_min": None, "price_max": None, "spicy": None},
            "ingredient_excludes": [],
            "soft_preferences": {"cuisine_affinity": [], "priority_order": []},
            "excluded_concepts": [],
            "semantic_attributes": [],
            "relationships": [],
            "follow_up": None,
            "context": {"party_size": 1, "conversation_ref": None},
        }

        try:
            executor_module.search_within_radius = recording_search
            result = tool_recommend_dishes_with_radius(
                user_id="user_01",
                keyword="phở",
                task_model=valid_task_model,
                initial_radius=5.0,
                max_radius=10.0,
            )
        finally:
            executor_module.search_within_radius = original_search

        assert radii[:2] == [5.0, 10.0], f"expected an automatic wider search, got radii {radii}"
        assert result["is_radius_expanded"] is True
        assert result["replan_trace"][0]["next_step"]["action"] == "expand_radius"
        assert result["candidates"]
