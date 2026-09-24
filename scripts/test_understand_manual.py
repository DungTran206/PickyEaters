# -*- coding: utf-8 -*-
"""
Quick manual test for the UNDERSTAND layer.
Shows whether LLM path or regex fallback is running, and prints TaskModel output.
"""
import os, sys, json
sys.stdout.reconfigure(encoding="utf-8")

from agent.understand import understand, _try_llm_understand

# Detect which path will be used
groq_key = os.getenv("GROQ_API_KEY", "").strip()
openai_key = os.getenv("OPENAI_API_KEY", "").strip()
path = "LLM (Groq)" if groq_key else ("LLM (OpenAI)" if openai_key else "REGEX FALLBACK")
print(f"=== UNDERSTAND path: {path} ===\n")

CASES = [
    # (input_text, description)
    ("muốn ăn xôi sườn gần nhà, không cay, dưới 40k",          "Basic: food + price + spicy"),
    ("không muốn ăn cơm, tìm gì đó ăn nhẹ thanh thanh",        "Negation + semantic attr"),
    ("phở bò với trà chanh cùng quán",                          "Composed order same_restaurant"),
    ("tôi thích đồ Hàn",                                        "State preference"),
    ("miến gà có không",                                         "Open-domain concept (not in FOOD_TERMS)"),
    ("muốn ăn gì đó nước nước, dễ nuốt thanh nhẹ",              "đồ nước + object semantic"),
    ("cay nhẹ nhẹ thôi, đừng cay quá",                         "Nuanced spicy → semantic, NOT hard constraint"),
    ("2 người dưới 150k, không cay",                            "Party size + price + spicy"),
    ("rẻ hơn đi",                                               "Follow-up: refine"),
    ("50k-100k muốn bún bò",                                    "Price range"),
    ("xin chào",                                                 "Chit-chat"),
    ("tao ghét hành",                                            "Ingredient exclude → state_preference"),
]

SEP = "-" * 60

for text, desc in CASES:
    print(f"{SEP}")
    print(f"[{desc}]")
    print(f"INPUT   : {text}")
    try:
        result = understand(text)
        print(f"intent  : {result.intent}")
        if result.objects:
            print(f"objects : {[(o.role, o.concept) for o in result.objects]}")
        if result.excluded_concepts:
            print(f"excluded: {result.excluded_concepts}")
        if result.ingredient_excludes:
            print(f"no-ingr : {result.ingredient_excludes}")
        hc = result.hard_constraints
        if any(v is not None for v in [hc.price_min, hc.price_max, hc.spicy]):
            print(f"hard    : price={hc.price_min}~{hc.price_max}  spicy={hc.spicy}")
        if result.soft_preferences.cuisine_affinity:
            print(f"cuisine : {result.soft_preferences.cuisine_affinity}")
        if result.soft_preferences.priority_order:
            print(f"priority: {result.soft_preferences.priority_order}")
        if result.semantic_attributes:
            print(f"semantic: {[(a.text, a.target, a.strength) for a in result.semantic_attributes]}")
        if result.relationships:
            print(f"relation: {[(r.type, r.objects) for r in result.relationships]}")
        if result.follow_up:
            print(f"followup: {result.follow_up}")
        if result.context.party_size > 1:
            print(f"party   : {result.context.party_size}")
    except Exception as e:
        print(f"ERROR   : {e}")
    print()

print(f"{SEP}")
print("Done.")
