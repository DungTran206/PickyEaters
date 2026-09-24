# -*- coding: utf-8 -*-
"""
Interactive REPL to test the UNDERSTAND layer from terminal.
Allows the user to enter food requests in Vietnamese and inspect the parsed TaskModel.
"""
import json
import os
import sys
import time

# Ensure UTF-8 output on Windows terminal without crashing on charmap errors
if sys.platform == "win32":
    os.system("")  # Enable VT100 escape sequences if available
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from agent.understand import understand, _try_llm_understand
from agent.task_model import TaskModel


def get_active_engine_info() -> tuple[str, bool]:
    """Check whether LLM credentials are configured."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if groq_key:
        model = os.getenv("OPENAI_MODEL_NAME", "qwen/qwen3.8-27b")
        return f"LLM [Groq API / {model}]", True
    elif openai_key:
        model = os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")
        return f"LLM [OpenAI API / {model}]", True
    else:
        return "Regex Fallback (Chua cau hinh API key trong .env)", False


def print_banner(engine_desc: str, is_llm: bool):
    print("=" * 66)
    print("  * PICKYEATERS — TEST BỘ PHÂN TÍCH NHU CẦU (UNDERSTAND REPL) *")
    print("=" * 66)
    print(f"[*] Engine hien tai : {engine_desc}")
    if not is_llm:
        print("[!] LUU Y: He thong dang chay 'Regex Fallback' vi chua co GROQ_API_KEY trong .env.")
        print("    De LLM hieu tieng Viet linh hoat nhat, ban chi can them vao .env:")
        print("    GROQ_API_KEY=gsk_xxx")
    print("-" * 66)
    print("[?] Huong dan:")
    print("  - Nhap cau yeu cau an uong bat ky (VD: 'them bun dau khong mam tom duoi 50k')")
    print("  - Go ':json' de BAT / TAT hien thi raw TaskModel JSON")
    print("  - Go 'q' hoac 'exit' de thoat")
    print("=" * 66)


def format_task_model(tm: TaskModel) -> str:
    """Format TaskModel into clean, human-readable terminal output."""
    lines = []

    # 1. Intent
    intent_vn = {
        "request_recommendation": "Gợi ý món / Tìm quán (request_recommendation)",
        "state_preference": "Khai báo sở thích / thói quen (state_preference)",
        "provide_info": "Bổ sung thông tin (provide_info)",
        "chit_chat": "Trò chuyện / Chào hỏi (chit_chat)",
    }.get(tm.intent, tm.intent)
    lines.append(f"  [>] Muc dich (Intent)           : {intent_vn}")

    # 2. Objects
    if tm.objects:
        obj_strs = []
        for o in tm.objects:
            req_str = "" if o.required else " (tuy chon)"
            obj_strs.append(f"[{o.role}] {o.concept}{req_str}")
        lines.append(f"  [+] Mon can tim (Objects)       : {', '.join(obj_strs)}")
    else:
        lines.append("  [+] Mon can tim (Objects)       : (khong co mon cu the)")

    # 3. Excluded Concepts
    if tm.excluded_concepts:
        lines.append(f"  [-] Mon khong muon an (Exclude) : {', '.join(tm.excluded_concepts)}")

    # 4. Ingredient Excludes
    if tm.ingredient_excludes:
        lines.append(f"  [x] Tranh nguyen lieu (No-Ingr) : {', '.join(tm.ingredient_excludes)}")

    # 5. Hard Constraints
    hc = tm.hard_constraints
    hc_parts = []
    if hc.price_min is not None or hc.price_max is not None:
        p_min = f"{hc.price_min:,}d" if hc.price_min is not None else "0d"
        p_max = f"{hc.price_max:,}d" if hc.price_max is not None else "khong gioi han"
        hc_parts.append(f"Gia: {p_min} ~ {p_max}")
    if hc.spicy is not None:
        hc_parts.append("Cay: Co" if hc.spicy else "Cay: Khong cay")
    if hc_parts:
        lines.append(f"  [!] Rang buoc cung (Hard Limit) : {', '.join(hc_parts)}")

    # 6. Semantic Attributes (cảm tính: cay nhẹ, thanh thanh, đồ nước, ngồi lâu...)
    if tm.semantic_attributes:
        attrs = [f'"{a.text}" ({a.target}/{a.strength})' for a in tm.semantic_attributes]
        lines.append(f"  [*] Cam tinh / Ngu nghia (Attr) : {', '.join(attrs)}")

    # 7. Soft Preferences
    sp = tm.soft_preferences
    sp_parts = []
    if sp.cuisine_affinity:
        sp_parts.append(f"Am thuc: {', '.join(sp.cuisine_affinity)}")
    if sp.priority_order:
        sp_parts.append(f"Uu tien: {', '.join(sp.priority_order)}")
    if sp_parts:
        lines.append(f"  [*] Uu tien mem (Preferences)   : {', '.join(sp_parts)}")

    # 8. Relationships
    if tm.relationships:
        rel_strs = [f"{r.type}(mon {r.objects})" for r in tm.relationships]
        lines.append(f"  [=] Quan he giua cac mon        : {', '.join(rel_strs)}")

    # 9. Follow-up
    if tm.follow_up:
        reason_str = f" - {tm.follow_up.reason}" if tm.follow_up.reason else ""
        lines.append(f"  [^] Phan hoi truoc (Follow-up)  : {tm.follow_up.type}{reason_str}")

    # 10. Context
    if tm.context.party_size > 1 or tm.context.conversation_ref:
        ctx_parts = []
        if tm.context.party_size > 1:
            ctx_parts.append(f"So nguoi: {tm.context.party_size}")
        if tm.context.conversation_ref:
            ctx_parts.append(f"Tham chieu: {tm.context.conversation_ref}")
        lines.append(f"  [@] Ngu canh (Context)          : {', '.join(ctx_parts)}")

    return "\n".join(lines)


def main():
    engine_desc, is_llm = get_active_engine_info()
    print_banner(engine_desc, is_llm)

    show_json = False

    while True:
        try:
            user_input = input("\n[>] Nhap yeu cau an uong > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTam biet!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("q", "quit", "exit"):
            print("Da thoat REPL.")
            break

        if user_input.lower() in (":json", "json"):
            show_json = not show_json
            state = "BAT" if show_json else "TAT"
            print(f"[*] Che do hien thi JSON: {state}")
            continue

        if user_input.lower() in ("help", "?"):
            print_banner(engine_desc, is_llm)
            continue

        # Execute understand
        t0 = time.perf_counter()
        llm_result = _try_llm_understand(user_input, [])
        if llm_result is not None:
            result = llm_result
            engine_used = "LLM"
        else:
            result = understand(user_input)
            engine_used = "Regex Fallback"
        elapsed = time.perf_counter() - t0

        print(f"\n+-- [KET QUA PHAN TICH: {engine_used} | {elapsed:.2f}s] " + "-" * (30 - len(engine_used)))
        print(format_task_model(result))
        print("+" + "-" * 65)

        if show_json:
            print("\n[Raw TaskModel JSON]:")
            print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
