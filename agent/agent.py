import json
import logging
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from agent.prompts import FOOD_AGENT_SYSTEM_PROMPT
from agent.tools import execute_tool
from agent.understand import understand
from agent.planner import plan_recommendation

load_dotenv()

logger = logging.getLogger(__name__)


class FoodAgent:
    def __init__(
        self,
        user_id: str = "user_01",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        force_mock: bool = False
    ):
        self.user_id = user_id

        # Detect Groq or OpenAI credentials
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        if api_key:
            self.api_key = api_key
        elif groq_key:
            self.api_key = groq_key
        else:
            self.api_key = openai_key

        is_groq = (
            bool(groq_key and not openai_key and not base_url)
            or (self.api_key and self.api_key.startswith("gsk_"))
            or ("groq.com" in (base_url or os.getenv("OPENAI_BASE_URL", "")).lower())
        )

        default_base_url = "https://api.groq.com/openai/v1" if is_groq else "https://api.openai.com/v1"
        default_model = "llama-3.3-70b-versatile" if is_groq else "gpt-4o-mini"

        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", default_base_url)
        self.model = model or os.getenv("OPENAI_MODEL_NAME", default_model)
        self.force_mock = force_mock

        # Conversation history kept for LLM reply-generation context only
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": FOOD_AGENT_SYSTEM_PROMPT}
        ]

        self.last_candidates: List[Dict[str, Any]] = []
        self.last_search_radius_km: float = 5.0
        self.last_is_radius_expanded: bool = False

        self.client = None
        if self.api_key and not self.force_mock:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except Exception as e:
                logger.warning("Failed to initialize OpenAI client: %s. Falling back to structured output.", e)
                self.client = None

    def reset_conversation(self):
        """Reset conversation history back to initial system prompt."""
        self.messages = [
            {"role": "system", "content": FOOD_AGENT_SYSTEM_PROMPT}
        ]
        self.last_candidates = []
        self.last_search_radius_km = 5.0
        self.last_is_radius_expanded = False

    def run(
        self,
        user_input: str,
        user_name: Optional[str] = None,
        user_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute one conversational turn.

        Architecture guarantee (AGENTS.md):
        Every turn goes through the SAME deterministic pipeline regardless of
        whether a real LLM client is available:

            UNDERSTAND → (TaskModel) → PLAN → ACT → COMPOSE → VALIDATE
                → RE-PLAN (bounded) → RANK → RESPOND

        The LLM (when available) is used ONLY in two places:
          1. UNDERSTAND: to extract TaskModel from raw user text.
          2. RESPOND: to compose a friendly reply wrapping structured output.

        Tool routing is NEVER delegated to the LLM's free tool-calling choice.
        """
        tool_call_logs: List[Dict[str, Any]] = []
        prior_candidates = self.last_candidates
        self.last_candidates = []
        self.last_search_radius_km = 5.0
        self.last_is_radius_expanded = False

        # ── Persist optional name / address updates ──────────────────────────
        if user_name:
            execute_tool("update_user_preference", {
                "user_id": self.user_id,
                "preference_type": "name",
                "value": user_name
            })
        if user_address:
            execute_tool("update_user_preference", {
                "user_id": self.user_id,
                "preference_type": "address",
                "value": user_address
            })

        # ── UNDERSTAND ────────────────────────────────────────────────────────
        last_shown = [
            {"ordinal": str(index), "name": candidate.get("dish", {}).get("name", "")}
            for index, candidate in enumerate(prior_candidates, 1)
        ]
        task_model = understand(user_input, last_shown)

        # ── Deterministic pipeline execution ─────────────────────────────────
        final_text = self._run_deterministic_pipeline(task_model, tool_call_logs, user_address)

        # ── Append to conversation history for LLM reply-generation context ──
        self.messages.append({"role": "user", "content": user_input})
        self.messages.append({"role": "assistant", "content": final_text})

        return {
            "response": final_text,
            "task_model": task_model.model_dump(mode="json"),
            "tool_calls": tool_call_logs,
            "candidates": self.last_candidates,
            "search_radius_km": self.last_search_radius_km,
            "is_radius_expanded": self.last_is_radius_expanded,
        }

    # =========================================================================
    # Unified pipeline — runs identically for LLM and no-LLM modes
    # =========================================================================

    def _run_deterministic_pipeline(
        self,
        task_model: Any,
        tool_call_logs: List[Dict[str, Any]],
        user_address: Optional[str] = None,
    ) -> str:
        """
        Single unified execution engine for ALL pipeline stages.

        Both LLM-available and no-LLM modes run through this same path.
        When self.client is available, the LLM generates the final reply text;
        otherwise the structured formatted output is returned directly.
        """
        # ── Step 1: Fetch profile (ACT – deterministic) ───────────────────────
        pref_args = {"user_id": self.user_id}
        pref = execute_tool("get_user_preferences", pref_args)
        tool_call_logs.append({"tool": "get_user_preferences", "arguments": pref_args, "result": pref})
        effective_address = user_address or pref.get("address") or "Cầu Giấy, Hà Nội"

        # ── Step 2: Non-recommendation intents ───────────────────────────────
        if task_model.intent == "state_preference":
            return self._handle_state_preference(task_model, tool_call_logs)

        if task_model.intent == "chit_chat":
            return self._respond_chit_chat(user_input=self.messages[-1].get("content", "") if self.messages else "")

        if task_model.intent == "provide_info":
            return "Tôi chưa có đủ ngữ cảnh để xác định quán hoặc món bạn đang hỏi."

        # ── Step 3: PLAN ──────────────────────────────────────────────────────
        rec_args = plan_recommendation(task_model, self.user_id, effective_address, pref)
        if rec_args is None:
            return "Tôi chưa rõ bạn đang muốn tìm món nào, bạn có thể nói cụ thể hơn không?"

        # ── Step 4: ACT → COMPOSE → VALIDATE → RE-PLAN → RANK ─────────────
        rec_result = execute_tool("recommend_dishes_with_radius", rec_args)
        tool_call_logs.append({
            "tool": "recommend_dishes_with_radius",
            "arguments": rec_args,
            "result": rec_result
        })

        self.last_candidates = rec_result.get("candidates", [])
        self.last_search_radius_km = rec_result.get("search_radius_km", 5.0)
        self.last_is_radius_expanded = rec_result.get("is_radius_expanded", False)

        structured_output = rec_result.get("formatted_text", "Đã tìm thấy món cho bạn!")

        # ── Step 5: RESPOND — LLM wraps the structured output (optional) ─────
        if self.client:
            return self._generate_llm_reply(structured_output)
        return structured_output

    # =========================================================================
    # Intent-specific handlers
    # =========================================================================

    def _handle_state_preference(
        self,
        task_model: Any,
        tool_call_logs: List[Dict[str, Any]],
    ) -> str:
        """Handle state_preference intent deterministically."""
        if task_model.ingredient_excludes:
            pref_type, value = "disliked_ingredients", task_model.ingredient_excludes[0]
        elif task_model.soft_preferences.cuisine_affinity:
            pref_type, value = "preferred_cuisines", task_model.soft_preferences.cuisine_affinity[0]
        elif task_model.hard_constraints.spicy is not None:
            pref_type, value = "preferred_flavors", "spicy" if task_model.hard_constraints.spicy else "non-spicy"
        else:
            return "Đã ghi nhận sở thích của bạn."
        args = {"user_id": self.user_id, "preference_type": pref_type, "value": value}
        result = execute_tool("update_user_preference", args)
        tool_call_logs.append({"tool": "update_user_preference", "arguments": args, "result": result})
        return result.get("message", "Đã cập nhật sở thích.")

    def _respond_chit_chat(self, user_input: str = "") -> str:
        """Return a short chit-chat reply. LLM can be used for natural variation."""
        if self.client and user_input:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Bạn là trợ lý tìm món ăn giao tận nơi. "
                                "Hãy trả lời ngắn gọn, thân thiện khi người dùng nói chuyện ngoài lề, "
                                "rồi khéo léo hỏi xem họ muốn ăn gì."
                            ),
                        },
                        {"role": "user", "content": user_input},
                    ],
                    max_tokens=150,
                    temperature=0.7,
                )
                return response.choices[0].message.content or "Tôi là trợ lý tìm món ăn. Bạn muốn ăn gì hôm nay?"
            except Exception as exc:
                logger.warning("[agent] chit_chat LLM call failed: %s", exc)
        return "Tôi là trợ lý tìm món ăn. Bạn muốn ăn gì hôm nay nhỉ?"

    def _generate_llm_reply(self, structured_output: str) -> str:
        """
        Use LLM to compose a friendly, natural-sounding reply that WRAPS
        (not replaces) the structured output produced by the deterministic pipeline.

        The LLM here acts as a RESPOND layer ONLY — it must not call tools or
        invent facts. It receives the already-formatted recommendation text and
        simply presents it in a conversational tone.
        """
        try:
            wrap_prompt = (
                "Dưới đây là kết quả từ hệ thống tìm kiếm món ăn (đã được tính toán và xác thực). "
                "Hãy trình bày lại cho người dùng một cách tự nhiên, thân thiện, ngắn gọn. "
                "KHÔNG thêm bất kỳ thông tin nào không có trong kết quả bên dưới. "
                "KHÔNG tự tạo tên quán, giá, rating. Giữ nguyên các số liệu đã có.\n\n"
                f"--- KẾT QUẢ ---\n{structured_output}"
            )
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": FOOD_AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": wrap_prompt},
                ],
                max_tokens=700,
                temperature=0.3,
            )
            return response.choices[0].message.content or structured_output
        except Exception as exc:
            logger.warning(
                "[agent] LLM reply generation failed (%s); using structured output directly.", exc
            )
            return structured_output
