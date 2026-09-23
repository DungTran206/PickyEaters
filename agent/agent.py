import json
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from agent.prompts import FOOD_AGENT_SYSTEM_PROMPT
from agent.tools import OPENAI_TOOLS, execute_tool
from agent.understand import understand
from agent.planner import plan_recommendation

load_dotenv()


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
                print(f"[Warning] Failed to initialize OpenAI client: {e}. Falling back to simulation mode.")
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
        Optionally updates persistent name and address if provided.
        Returns response, tool calls, and structured candidates.
        """
        tool_call_logs = []
        prior_candidates = self.last_candidates
        self.last_candidates = []
        self.last_search_radius_km = 5.0
        self.last_is_radius_expanded = False

        # Update name and address in DB if provided
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

        last_shown = [
            {"ordinal": str(index), "name": candidate.get("dish", {}).get("name", "")}
            for index, candidate in enumerate(prior_candidates, 1)
        ]
        task_model = understand(user_input, last_shown)
        self.messages.append({
            "role": "user",
            "content": "TaskModel cho lượt hiện tại:\n" + json.dumps(task_model.model_dump(mode="json"), ensure_ascii=False),
        })

        if self.client:
            final_text = self._run_llm_loop(tool_call_logs)
        else:
            final_text = self._run_mock_loop(task_model, tool_call_logs, user_address=user_address)

        self.messages.append({"role": "assistant", "content": final_text})
        return {
            "response": final_text,
            "task_model": task_model.model_dump(mode="json"),
            "tool_calls": tool_call_logs,
            "candidates": self.last_candidates,
            "search_radius_km": self.last_search_radius_km,
            "is_radius_expanded": self.last_is_radius_expanded,
        }

    def _run_llm_loop(self, tool_call_logs: List[Dict[str, Any]], max_turns: int = 8) -> str:
        """Execute real LLM tool-calling loop."""
        for _ in range(max_turns):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto"
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                self.messages.append(msg.model_dump())
                for call in msg.tool_calls:
                    func_name = call.function.name
                    try:
                        func_args = json.loads(call.function.arguments)
                    except Exception:
                        func_args = {}

                    try:
                        result = execute_tool(func_name, func_args)
                    except Exception as ex:
                        result = {"error": str(ex)}

                    # Capture candidates and radius info from tools
                    if isinstance(result, dict) and "candidates" in result:
                        self.last_candidates = result["candidates"]
                        self.last_search_radius_km = result.get("search_radius_km", 5.0)
                        self.last_is_radius_expanded = result.get("is_radius_expanded", False)

                    tool_call_logs.append({
                        "tool": func_name,
                        "arguments": func_args,
                        "result": result
                    })

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result, ensure_ascii=False)
                    })
            else:
                return msg.content or ""

        return "Tôi đã phân tích và tìm kiếm xong cho bạn rồi nè!"

    def _run_mock_loop(
        self,
        task_model: Any,
        tool_call_logs: List[Dict[str, Any]],
        user_address: Optional[str] = None
    ) -> str:
        """
        Deterministic autonomous fallback loop simulating LLM tool calls.
        Executes actual tools sequentially and formats output according to instructions.
        """
        pref_args = {"user_id": self.user_id}
        pref = execute_tool("get_user_preferences", pref_args)
        tool_call_logs.append({"tool": "get_user_preferences", "arguments": pref_args, "result": pref})
        effective_address = user_address or pref.get("address") or "Cầu Giấy, Hà Nội"
        if task_model.intent == "state_preference":
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

        if task_model.intent == "chit_chat":
            return "Tao đây. Mày muốn tìm món gì?"
        if task_model.intent == "provide_info":
            return "Tao chưa có đủ ngữ cảnh để xác định quán hoặc món mày đang hỏi."

        rec_args = plan_recommendation(task_model, self.user_id, effective_address, pref)
        if rec_args is None:
            return "Tao chưa rõ mày đang muốn tìm món nào."
        rec_result = execute_tool("recommend_dishes_with_radius", rec_args)
        tool_call_logs.append({
            "tool": "recommend_dishes_with_radius",
            "arguments": rec_args,
            "result": rec_result
        })

        self.last_candidates = rec_result.get("candidates", [])
        self.last_search_radius_km = rec_result.get("search_radius_km", 5.0)
        self.last_is_radius_expanded = rec_result.get("is_radius_expanded", False)

        return rec_result.get("formatted_text", "Đã tìm thấy món cho bạn!")
