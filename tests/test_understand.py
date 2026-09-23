"""
Tests for the UNDERSTAND layer.

Covers:
1. LLM path: mocks the OpenAI client to verify JSON parsing + validation.
2. Regex fallback: verifies behavior when LLM is unavailable.
3. Edge cases that motivated the LLM migration (open-domain food concepts).
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agent.task_model import TaskModel
from agent.understand import _parse_and_validate, _regex_understand, understand


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_response(task_dict: dict) -> MagicMock:
    """Build a minimal mock that mimics openai.ChatCompletion response."""
    content = json.dumps(task_dict, ensure_ascii=False)
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    response = MagicMock()
    response.choices = [choice]
    return response


def _base_task(**overrides) -> dict:
    """Minimal valid TaskModel dict."""
    base = {
        "intent": "request_recommendation",
        "objects": [],
        "hard_constraints": {"price_min": None, "price_max": None, "spicy": None},
        "ingredient_excludes": [],
        "soft_preferences": {"cuisine_affinity": [], "priority_order": []},
        "excluded_concepts": [],
        "semantic_attributes": [],
        "relationships": [],
        "follow_up": None,
        "context": {"party_size": 1, "conversation_ref": None},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# _parse_and_validate unit tests (no network)
# ---------------------------------------------------------------------------

class TestParseAndValidate:
    def test_clean_json_parses_correctly(self):
        data = _base_task(objects=[{"role": "Main", "concept": "xôi sườn", "required": True}])
        result = _parse_and_validate(json.dumps(data))
        assert result is not None
        assert result.objects[0].concept == "xôi sườn"

    def test_strips_markdown_fence(self):
        data = _base_task()
        raw = f"```json\n{json.dumps(data)}\n```"
        assert _parse_and_validate(raw) is not None

    def test_returns_none_on_invalid_json(self):
        assert _parse_and_validate("not json at all") is None

    def test_returns_none_on_pydantic_violation(self):
        # price_min > price_max must fail
        bad = _base_task()
        bad["hard_constraints"] = {"price_min": 100000, "price_max": 30000, "spicy": None}
        assert _parse_and_validate(json.dumps(bad)) is None

    def test_returns_none_on_invalid_relationship_index(self):
        bad = _base_task(
            objects=[{"role": "Main", "concept": "phở", "required": True}],
            relationships=[{"type": "same_order", "objects": [0, 1]}],  # index 1 out of range
        )
        assert _parse_and_validate(json.dumps(bad)) is None


# ---------------------------------------------------------------------------
# LLM path (mocked)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_env_key(monkeypatch):
    """Inject a fake Groq key so LLM path is attempted."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_fake_key")


class TestLLMPath:
    def _call_with_mock_response(self, task_dict: dict, user_text: str = "test") -> TaskModel:
        mock_response = _make_llm_response(task_dict)
        with patch("agent.understand.OpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create.return_value = mock_response
            result = understand(user_text)
        return result

    def test_llm_result_is_used_when_available(self):
        data = _base_task(
            objects=[{"role": "Main", "concept": "bún đậu mắm tôm", "required": True}]
        )
        result = self._call_with_mock_response(data, "muốn ăn bún đậu mắm tôm")
        assert result.objects[0].concept == "bún đậu mắm tôm"

    def test_open_domain_concept_preserved(self):
        """LLM should extract food concepts not in the hardcoded FOOD_TERMS list."""
        data = _base_task(
            objects=[{"role": "Main", "concept": "miến gà", "required": True}]
        )
        result = self._call_with_mock_response(data, "muốn ăn miến gà")
        assert result.objects[0].concept == "miến gà"

    def test_nuanced_spicy_goes_to_semantic_not_hard_constraint(self):
        data = _base_task(
            semantic_attributes=[{"text": "cay nhẹ", "strength": "soft", "target": "object"}]
        )
        result = self._call_with_mock_response(data, "muốn ăn gì đó cay nhẹ")
        assert result.hard_constraints.spicy is None
        assert any(a.text == "cay nhẹ" for a in result.semantic_attributes)

    def test_negated_food_no_object(self):
        data = _base_task(
            excluded_concepts=["cơm"],
            objects=[{"role": "Main", "concept": None, "required": True}],
        )
        result = self._call_with_mock_response(data, "không muốn ăn cơm, tìm gì khác")
        assert "cơm" in result.excluded_concepts
        assert not any(obj.concept == "cơm" for obj in result.objects)

    def test_semantic_attribute_do_nuoc_is_main_not_drink(self):
        data = _base_task(
            objects=[{"role": "Main", "concept": None, "required": True}],
            semantic_attributes=[{"text": "đồ nước", "strength": "soft", "target": "object"}],
        )
        result = self._call_with_mock_response(data, "muốn ăn đồ nước")
        assert result.objects[0].role == "Main"
        assert any(a.text == "đồ nước" for a in result.semantic_attributes)

    def test_price_extraction(self):
        data = _base_task(
            hard_constraints={"price_min": None, "price_max": 50000, "spicy": False},
            objects=[{"role": "Main", "concept": "phở", "required": True}],
        )
        result = self._call_with_mock_response(data, "phở không cay dưới 50k")
        assert result.hard_constraints.price_max == 50000
        assert result.hard_constraints.spicy is False

    def test_state_preference_intent(self):
        data = _base_task(
            intent="state_preference",
            soft_preferences={"cuisine_affinity": ["Korean"], "priority_order": []},
        )
        result = self._call_with_mock_response(data, "tôi thích đồ Hàn")
        assert result.intent == "state_preference"
        assert "Korean" in result.soft_preferences.cuisine_affinity

    def test_composed_order_relationship(self):
        data = _base_task(
            objects=[
                {"role": "Main", "concept": "cơm tấm", "required": True},
                {"role": "Drink", "concept": "trà sữa", "required": True},
            ],
            relationships=[{"type": "same_order", "objects": [0, 1]}],
        )
        result = self._call_with_mock_response(data, "cơm tấm với trà sữa")
        assert len(result.objects) == 2
        assert result.relationships[0].type == "same_order"

    def test_fallback_to_regex_on_llm_error(self, monkeypatch):
        """If LLM raises, regex fallback must return a valid TaskModel."""
        with patch("agent.understand.OpenAI") as MockClient:
            MockClient.side_effect = Exception("network error")
            result = understand("muốn ăn phở")
        assert isinstance(result, TaskModel)
        assert result.intent == "request_recommendation"

    def test_fallback_to_regex_on_bad_json(self):
        """If LLM returns garbage JSON, regex fallback kicks in."""
        with patch("agent.understand.OpenAI") as MockClient:
            instance = MockClient.return_value
            bad_msg = SimpleNamespace(content="sorry I cannot help with that")
            instance.chat.completions.create.return_value = MagicMock(
                choices=[SimpleNamespace(message=bad_msg)]
            )
            result = understand("xôi")
        assert isinstance(result, TaskModel)
        assert result.intent == "request_recommendation"


# ---------------------------------------------------------------------------
# Regex fallback path (no LLM)
# ---------------------------------------------------------------------------

class TestRegexFallback:
    """These tests verify the regex path directly (no mocking needed)."""

    def test_xoi_recognized(self):
        task = _regex_understand("muốn ăn xôi", [])
        assert task.intent == "request_recommendation"
        concepts = [o.concept for o in task.objects]
        assert "xôi" in concepts

    def test_negation_priority(self):
        task = _regex_understand("không muốn ăn cơm", [])
        assert "cơm" in task.excluded_concepts
        assert all(o.concept != "cơm" for o in task.objects)

    def test_do_nuoc_is_main_not_drink(self):
        task = _regex_understand("muốn đồ nước", [])
        assert task.objects[0].role == "Main"
        assert task.objects[0].concept is None

    def test_price_range(self):
        task = _regex_understand("40k-80k muốn cơm với trà chanh", [])
        assert task.hard_constraints.price_min == 40000
        assert task.hard_constraints.price_max == 80000

    def test_ingredient_exclude_separated_from_concept(self):
        task = _regex_understand("tao ghét hành", [])
        assert task.ingredient_excludes == ["hành"]
        assert task.excluded_concepts == []
