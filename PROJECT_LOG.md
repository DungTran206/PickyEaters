# PROJECT LOG — PickyEaters Food Agent
> **Bộ não thứ 2** — ghi lại mọi quyết định kiến trúc, cải tiến từng component, vấn đề tồn đọng và hướng tiếp theo.
> Cập nhật sau mỗi sprint / session làm việc.

---

## 📌 Nguyên tắc cốt lõi (bất biến)
Pipeline: `UNDERSTAND → TaskModel → PLAN → ACT → OBSERVE → VALIDATE → RE-PLAN → COMPOSE → RANK → RESPOND`

- **UNDERSTAND** sở hữu toàn bộ việc parse ngôn ngữ tự nhiên → ra `TaskModel`.
- **TaskModel** là contract duy nhất giữa NLU và các layer sau.
- Không được parse lại raw text ở downstream.
- Không fabricate dữ liệu nhà hàng/món từ LLM.
- Hard constraints không được âm thầm relaxed.

---

## 🗓️ Session Log

---

### Session 1 — Khởi tạo & Data Foundation
**Date:** 2026-09-21

#### Vấn đề phát hiện
- Tìm "xôi" ra phở bún → keyword matching quá rộng, không có word boundary.
- Tìm ở Thanh Xuân ra quán Hồ Chí Minh với khoảng cách 4.7km giả → geocoding không scope theo thành phố.
- Data quá nghèo nàn, thiếu quán thực tế ở Thanh Xuân.

#### Thay đổi thực hiện
| File | Thay đổi |
|------|----------|
| `services/search.py` | Fix geocoding: scope district search theo Hà Nội/HCM; thêm `KEYWORD_SYNONYMS` với regex word boundary |
| `services/recommendation.py` | Refactor `rank_candidates`: sort theo Rating khi có keyword cụ thể; enforce restaurant diversity top-K |
| `agent/agent.py` | Thêm compound dish keywords (xôi gà, cơm tấm, …) vào recognition loop |
| `data/` | Crawl & seed 20 quán Thanh Xuân + 60 món + 6 promo |

#### Kết quả
- Tìm xôi → ra xôi đúng quán đúng phường.
- Geocoding không còn cross-city.

---

### Session 2 — Kiến trúc & Docs
**Date:** 2026-09-21

#### Thực hiện
- Tạo `PIPELINE_ARCHITECTURE.md` — sơ đồ luồng đầy đủ.
- Tạo `README.md` — hướng dẫn cài đặt, API, kiến trúc tổng quan.
- Push lên GitHub: https://github.com/DungTran206/PickyEaters

---

### Session 3 — UNDERSTAND Component: LLM-based NLU
**Date:** 2026-09-23

#### Vấn đề
`understand.py` hiện tại dùng **regex thuần** để:
- Detect intent
- Extract food objects (list cứng `FOOD_TERMS`)
- Parse price, spicy, exclusions, cuisine...

**Hệ quả:** Bất kỳ món/cụm từ nào nằm ngoài `FOOD_TERMS` đều bị bỏ qua. LLM không thực sự hiểu ngữ nghĩa tiếng Việt.

#### Hướng tiếp cận chọn
**LLM Structured Extraction** (Hướng 1):
- Dùng LLM (Groq / OpenAI) với JSON Schema / function calling để extract `TaskModel`.
- Fallback graceful về regex-path nếu không có LLM key.
- Prompt viết tiếng Việt, dạy LLM hiểu ngữ nghĩa đặc thù VN (đồ nước, ăn nhẹ, cay nhẹ...).
- Validate output bằng Pydantic `TaskModel` trước khi tiếp tục.

#### Thay đổi thực hiện
| File | Thay đổi |
|------|----------|
| `agent/understand.py` | Rewrite: thêm `understand_llm()` làm primary path; giữ regex làm fallback |
| `agent/prompts.py` | Thêm `UNDERSTAND_SYSTEM_PROMPT` cho NLU |

#### Contract đầu ra (không thay đổi)
`understand(user_text, last_shown_candidates) -> TaskModel` — interface không đổi với `agent.py`.

#### Kết quả mong đợi
- "muốn ăn gì đó thanh thanh, không nhiều dầu mỡ" → `semantic_attributes` đúng.
- "xôi sườn hay cơm tấm gì đó rẻ rẻ thôi" → `objects: [{concept: xôi sườn}, {concept: cơm tấm}]`.
- "không muốn ăn cơm" → `excluded_concepts: [cơm]`, không có object nào là cơm.

---

## 🐛 Known Issues / Debt

| ID | Component | Mô tả | Ưu tiên |
|----|-----------|-------|---------|
| BUG-01 | `understand.py` | FOOD_TERMS list hardcode → miss nhiều món | **Đang sửa** |
| BUG-02 | `services/search.py` | Geocoding vẫn fallback dummy khi không có Nominatim | Medium |
| DEBT-01 | `agent/agent.py` | Mock loop không dùng TaskModel đầy đủ (bỏ qua relationships, semantic_attrs) | Low |
| DEBT-02 | `services/recommendation.py` | Reasoning text không mention cuisine khi không match spicy | Low |

---

## 📋 Component Status

| Component | Layer | Status | Notes |
|-----------|-------|--------|-------|
| `understand.py` | UNDERSTAND | 🔧 In Progress | Migrating to LLM extraction |
| `task_model.py` | Contract | ✅ Stable | Pydantic schema validated |
| `planner.py` | PLAN | ✅ Basic | Translates TaskModel → tool args |
| `tools.py` | ACT | ✅ Working | `recommend_dishes_with_radius` |
| `services/search.py` | ACT | ✅ Fixed | Geocoding scoped, keyword boundary fixed |
| `services/recommendation.py` | RANK | ✅ Working | Rating-based sort + diversity |
| VALIDATE | VALIDATE | ❌ Missing | Hard constraint check not standalone |
| RE-PLAN | RE-PLAN | ⚠️ Basic | Only radius expansion |
| COMPOSE | COMPOSE | ❌ Missing | Multi-object orders not composed |

---

## 🔮 Next Priorities (Backlog)

1. **[NOW] UNDERSTAND** — LLM structured extraction (current sprint)
2. **[NEXT] VALIDATE** — Tách validate thành module riêng, enforce hard constraints explicitly
3. **[NEXT] RE-PLAN** — Bounded replan loop: không chỉ mở rộng radius mà còn relax soft prefs
4. **[LATER] COMPOSE** — Multi-object ordering với budget check sau composition
5. **[LATER] Real geocoding** — Nominatim / Google Maps thay dummy coordinates
6. **[LATER] Real data** — Scraper thực tế thay seed data tĩnh
