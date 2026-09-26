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
| `agent/understand.py` | Rewrite: thêm `_try_llm_understand()` làm primary path; giữ regex làm fallback |
| `agent/prompts.py` | Thêm `UNDERSTAND_SYSTEM_PROMPT` cho NLU tiếng Việt |
| `tests/test_understand.py` | 20 unit tests (LLM mocked + regex fallback) |
| `scripts/repl_understand.py` | CLI REPL tương tác trực tiếp trên terminal để người dùng tự kiểm tra NLU |
| `scripts/test_understand_manual.py` | Script test tự động với 12 test case mẫu |

#### Contract đầu ra (không thay đổi)
`understand(user_text, last_shown_candidates) -> TaskModel` — interface không đổi với `agent.py`.

#### Công cụ tự kiểm tra trên Terminal:
- Chạy: `python -m scripts.repl_understand`
- Cho phép gõ câu tự do, xem phân tích trực quan hoặc xem raw JSON (gõ `:json`).

---

## 🐛 Known Issues / Debt

| ID | Component | Mô tả | Ưu tiên |
|----|-----------|-------|---------|
| BUG-01 | `understand.py` | FOOD_TERMS list hardcode → miss nhiều món | **Đang sửa** |
| BUG-02 | `services/search.py` | Geocoding vẫn fallback dummy khi không có Nominatim | Medium |
| DEBT-01 | `agent/agent.py` | Mock loop không dùng TaskModel đầy đủ (bỏ qua relationships, semantic_attrs) | Low |
| DEBT-02 | `services/recommendation.py` | Reasoning text không mention cuisine khi không match spicy | Low |

---

### Session 4 — Tinh chỉnh UNDERSTAND theo nghiệp vụ Food Delivery
**Date:** 2026-09-24

#### Quyết định nghiệp vụ quan trọng từ User:
1. **Bản chất hệ thống**: Đây là nền tảng **tư vấn đặt món ăn giao tận nơi (Food Delivery)** qua app (như ShopeeFood/GrabFood), KHÔNG phải tìm quán ăn tại chỗ.
2. **Loại bỏ `venue`**: Target của `SemanticAttribute` chỉ còn 2 loại:
   - `object`: Thuộc tính món ăn (thanh đạm, cay nhẹ, đồ nước, giòn tan, ít ngọt, nhiều đạm...).
   - `order`: Thuộc tính đơn hàng / bữa ăn (ăn trưa nhanh, ăn xế, ăn đêm nhẹ bụng, no lâu, giải bia rượu...).
   - Loại bỏ hoàn toàn các thuộc tính quán ngồi tại chỗ (như ngồi lâu, view đẹp, điều hoà).
3. **Trọng tâm hiện tại**: Tiếp tục tập trung tối đa vào tầng **UNDERSTAND** để hiểu thật sâu và phân tích chuẩn xác ngôn ngữ người dùng Việt Nam khi đặt đồ ăn về. Tạm hoãn việc xây tầng validate dị ứng/ràng buộc cứng.
4. **Fix Rate Limit Groq**: Đổi `max_tokens` từ 1024 về 500 để không vượt ngưỡng OTPM 1000 của Groq on-demand free tier.

| File | Thay đổi |
|------|----------|
| `agent/task_model.py` | Đổi `target: Literal["object", "order"]` (loại bỏ `venue`) |
| `agent/prompts.py` | Cập nhật system prompt định hình rõ trợ lý Food Delivery, chuẩn hóa quy tắc target `object` / `order` |
| `agent/understand.py` | Loại bỏ `venue` khỏi fallback regex, hạ `max_tokens=500` tránh lỗi OTPM 1000 |
| `tests/conftest.py` | Thêm mock API key để bảo đảm 51 unit tests chạy độc lập và không tốn quota |

---

### Session 5 — Nâng cấp tầng PLAN (Semantic Category Mapping & Multi-Object Decomposition)
**Date:** 2026-09-24

#### Thay đổi thực hiện:
1. **Năng lực Ánh xạ Ngữ nghĩa (Semantic Category Mapping)**:
   - Khi người dùng không nêu tên món cụ thể (`concept = None`) mà chỉ nói cảm tính (ví dụ: *"muốn ăn đồ nước"*, *"thanh đạm"*, *"ăn nhẹ"*, *"chắc bụng"*, *"ăn no"*):
   - [agent/planner.py](agent/planner.py) tự động phân giải `semantic_attributes` thành danh mục các từ khóa món ăn (`semantic_keywords`: phở, bún, miến, cháo, súp...).
   - [services/search.py](services/search.py) và [agent/tools.py](agent/tools.py) tiếp nhận `semantic_keywords` để lọc chuẩn xác món dạng nước, không còn bị trả về món khô hay cơm xôi ngẫu nhiên.
2. **Khắc phục lỗi nhầm lẫn ngữ nghĩa ẩm thực (Vietnamese Food Disambiguation)**:
   - `phở`: Không bị nhầm sang `phô mai` (cheese) hoặc `phố cổ` (street name).
   - `miến`: Không bị nhầm sang `miền nam / miền bắc / miền tây` (địa lý).
   - `cháo`: Không bị nhầm sang `chảo / trên chảo nóng` (dụng cụ nấu).
   - `canh`: Không bị nhầm sang `cánh gà` / `màu cánh gián`.
3. **Phân rã đơn nhiều món (Multi-Object Decomposition)**:
   - Tách món chính (`keyword`) và món phụ/nước uống (`secondary_keywords`).
   - Tự động nhận diện chiến lược giao hàng cùng quán (`composition_strategy: "same_restaurant"`).
4. **Kiểm thử**:
   - Tạo file unit test chuyên biệt [tests/test_planner.py](tests/test_planner.py) (7 tests).
   - Toàn bộ suite **58/58 tests passed 100%**.

| File | Thay đổi |
|------|----------|
| `agent/planner.py` | Viết lại logic lập kế hoạch: `resolve_semantic_keywords`, phân rã đa món, chiến lược gom đơn |
| `services/search.py` | Hỗ trợ `semantic_keywords` trong `search_dishes` và `search_with_radius_expansion`; bổ sung disambiguation cho phở/miến/cháo/canh |
| `agent/tools.py` | Cập nhật `tool_recommend_dishes_with_radius` nhận `semantic_keywords` & `secondary_keywords` |
| `tests/test_planner.py` | Thêm 7 unit tests kiểm tra toàn diện tầng PLAN |

---

### Session 6 — Nâng cấp tầng RANK & RESPOND (Chấm điểm ngữ nghĩa & Giải thích minh bạch)
**Date:** 2026-09-24

#### Thay đổi thực hiện:
1. **Chấm điểm ngữ nghĩa cảm tính (`semantic_score`)**:
   - [services/recommendation.py](services/recommendation.py) bổ sung hàm `evaluate_semantic_match`:
     - *"đồ nước / nước dùng"*: Thưởng +3.0 điểm cho phở/bún/miến/cháo có nước, phạt -2.0 nếu là món khô (cơm, xôi, bánh mì).
     - *"thanh thanh / thanh đạm / nhẹ bụng"*: Thưởng +2.5 điểm cho món luộc, hấp, cháo, cuốn, canh; phạt -2.0 cho món mỡ ngấy (thịt kho, chiên giòn, xôi mỡ).
     - *"ăn no / chắc bụng"*: Thưởng +2.5 điểm cho cơm, xôi, bún đậu, mì xào.
     - *"cay nhẹ / hơi cay"*: Thưởng +2.0 điểm nếu món the cay êm dịu, không phạt nếu không cay gắt.
     - *"ăn trưa nhanh / gọn nhẹ"*: Thưởng +1.5 điểm cho các món tiện lợi văn phòng.
2. **Sinh lời giải thích minh bạch (Explainable Reasoning)**:
   - Tầng **RESPOND** trích xuất lý do gợi ý trực tiếp vào từng thẻ món ăn:
     `🍃 Chuẩn vị thanh đạm: thanh nhẹ dễ nuốt, êm bụng không gây ngấy`
     hoặc `🍜 Chuẩn điệu món nước: nước dùng nóng hổi, xì xụp đậm đà giải ngấy`.
3. **Kiểm thử tự động**:
   - Tạo bộ unit test [tests/test_recommendation.py](tests/test_recommendation.py) (5 tests) kiểm tra toàn diện điểm ngữ nghĩa, đẩy món khớp cảm tính lên Top 1 và hiển thị giải thích.
   - Toàn bộ test suite **63/63 tests passed 100%**.

| File | Thay đổi |
|------|----------|
| `services/recommendation.py` | Thêm `evaluate_semantic_match`, trường `semantic_score`, bullet point cảm tính trong `generate_detailed_reasoning`, hỗ trợ lookup `restaurants` |
| `tests/test_recommendation.py` | Tạo mới 5 unit tests kiểm thử logic xếp hạng cảm tính và giải thích |

---

---

### Session 7 — Xây dựng tầng COMPOSE (Ghép đơn Combo đa món cùng quán & Xác thực ngân sách hậu kỳ)
**Date:** 2026-09-24

#### Thay đổi thực hiện:
1. **Khởi tạo Module `agent/composer.py`**:
   - `is_composed_order_request`: Nhận diện đơn yêu cầu nhiều món (`len(task.objects) > 1`) và có quan hệ `same_restaurant` / `same_order` hoặc có `role` là `Drink` / `Side`.
   - `match_dish_to_task_object`: So khớp món ăn với đối tượng yêu cầu (theo concept, vai trò Role, và phân loại Category: Main/Drink/Side). Ngăn chặn việc gán nhầm món phụ/nước vào vai trò món chính.
   - `compose_candidates`:
     - Gom nhóm các món tìm kiếm được theo từng nhà hàng (`restaurant_id`).
     - Chỉ tạo combo đối với những quán có đồng thời đầy đủ món chính và các món phụ/đồ uống yêu cầu.
     - Tính tổng bill combo (`subtotal`), áp dụng voucher khuyến mãi tối ưu nhất trên toàn bộ đơn hàng.
     - **Chỉ tính 1 lần phí ship duy nhất (`delivery_fee`)** cho cả combo từ cùng 1 quán thay vì nhân đôi.
     - **Xác thực ngân sách hậu kỳ (Post-composition Budget Validation - Rule 8 trong AGENTS.md)**: Kiểm tra `subtotal` và `final_price` với `hard_constraints.price_max` trên tổng toàn đơn combo. Loại bỏ ngay những combo vượt ngân sách.
2. **Nâng cấp `services/recommendation.py` & `agent/tools.py`**:
   - `RecommendationCandidate` bổ sung trường `items: List[Dish]` để đại diện cho combo nhiều món (tương thích 100% với đơn 1 món).
   - `format_recommendations_output`: Thiết kế giao diện thẻ Combo chuyên nghiệp:
     - Tên combo: `Combo: [Món chính] + [Món phụ/Đồ uống] — [Tên quán]`
     - Chi tiết từng món & giá niêm yết
     - Tổng đơn, voucher tiết kiệm, phí ship chung 1 lần
     - Lý do gợi ý: Tiết kiệm phí ship khi đặt cùng quán, đúng gu...
   - `search_with_radius_expansion` tiếp nhận `secondary_keywords` để quét thêm các món phụ/đồ uống của các quán ứng viên.
3. **Sửa lỗi ngầm (Bugfix) trong Synonym Matching**:
   - Khắc phục lỗi trong `services/search.py`: Khi user tìm món cụ thể (như `phở bò`), synonym không còn bị mở rộng ngược về gốc `phở` làm khớp nhầm sang `quẩy giòn phở` hay `phở gà`.
   - Xóa `nem cua bể` khỏi synonym của `bún chả`.
4. **Kiểm thử tự động**:
   - Tạo file unit test chuyên biệt [tests/test_composer.py](tests/test_composer.py) (6 tests).
   - Toàn bộ test suite **69/69 tests passed 100%**.

| File | Thay đổi |
|------|----------|
| `agent/composer.py` | Tạo mới module COMPOSE phụ trách ghép combo cùng quán và xác thực ngân sách hậu kỳ |
| `database/models.py` | Thêm trường `items: List[Dish]` vào `RecommendationCandidate` |
| `services/search.py` | Hỗ trợ `secondary_keywords` trong `search_with_radius_expansion`; fix synonym expansion |
| `agent/tools.py` | Tích hợp `compose_candidates` trong `tool_recommend_dishes_with_radius` |
| `services/recommendation.py` | Hỗ trợ `precomputed_candidates` trong `rank_candidates` và định dạng hiển thị combo trong `format_recommendations_output` |
| `tests/test_composer.py` | Tạo mới 6 unit tests kiểm thử toàn diện tầng COMPOSE |

---

---

### Session 8 — Xây dựng tầng VALIDATE độc lập & Tối ưu Chit-Chat
**Date:** 2026-09-24

#### Thay đổi thực hiện:
1. **Khởi tạo Module `agent/validator.py`**:
   - Tuân thủ nguyên tắc số 6 trong `AGENTS.md`: *"VALIDATE owns hard-constraint checking. Hard constraints must not be silently relaxed."*
   - Cung cấp mô hình dữ liệu bằng chứng lỗi có cấu trúc:
     - `ConstraintViolation`: Ghi rõ loại vi phạm (`price_max`, `price_min`, `spicy`, `ingredient_exclude`, `excluded_concept`), trường dữ liệu, thông điệp lỗi, giá trị thực tế của món vs. giá trị mong muốn của user.
     - `ValidationResult`: Chứa boolean `is_valid` và danh sách vi phạm `violations`.
   - `validate_candidate`: Kiểm tra từng candidate (món đơn hoặc combo) với tất cả các ràng buộc cứng:
     - Ngân sách tối đa `price_max` (kiểm tra cả subtotal và final_price).
     - Mức giá tối thiểu `price_min`.
     - Độ cay `spicy` (phát hiện cả trường hợp user yêu cầu không cay nhưng món cay, hoặc yêu cầu món cay nhưng đơn không có món cay nào).
     - Nguyên liệu kiêng `ingredient_excludes` (kết hợp cả từ `TaskModel` và durable `UserPreference`).
     - Món cấm / loại trừ `excluded_concepts` (ví dụ: cấm ăn xôi / cơm).
   - `validate_candidates_list`: Phân tách danh sách ứng viên thành `valid_candidates` và `rejected_candidates` kèm theo bằng chứng lỗi chi tiết — làm dữ liệu đầu vào có cấu trúc cho tầng **RE-PLAN**.
2. **Tích hợp vào luồng thực thi `agent/tools.py`**:
   - `tool_recommend_dishes_with_radius` kích hoạt `validate_candidates_list` để sàng lọc sạch sẽ mọi ứng viên trước khi chuyển sang tầng hiển thị/xếp hạng.
3. **Tối ưu phản hồi cho câu hỏi ngoài lề (Chit-Chat)**:
   - Khi người dùng nhập câu không liên quan ẩm thực (*"ngoài trời đang mưa hay nắng"*):
     - `UNDERSTAND` phân loại chính xác `intent: "chit_chat"`, không sinh `objects` hay ràng buộc giả mạo.
     - `PLAN` chặn hoàn toàn việc gọi search tools, tiết kiệm tài nguyên.
     - `agent/agent.py`: Bổ sung `max_tokens=400` cho `chat.completions.create` để không bị vượt ngưỡng OTPM 1000 của Groq on-demand free tier.
4. **Kiểm thử tự động**:
   - Tạo file unit test chuyên biệt [tests/test_validator.py](tests/test_validator.py) (7 tests).
   - Toàn bộ test suite **76/76 tests passed 100%**.

| File | Thay đổi |
|------|----------|
| `agent/validator.py` | Tạo mới module VALIDATE độc lập kiểm tra hard constraints và sinh ConstraintViolation có cấu trúc |
| `agent/tools.py` | Tích hợp `validate_candidates_list` trước khi định dạng và xếp hạng |
| `agent/agent.py` | Đặt `max_tokens=400` tránh lỗi OTPM 1000 của Groq trong luồng hội thoại |
| `tests/test_validator.py` | Tạo mới 7 unit tests kiểm thử toàn diện tầng VALIDATE |

---

### Session 9 (2026-09-24) — Tầng RE-PLAN Loop (Phản hồi thích ứng dựa trên bằng chứng lỗi có cấu trúc)

1. **Triển khai kiến trúc RE-PLAN có cấu trúc (`agent/replan.py`)**:
   - Tuân thủ nguyên tắc số 6 và số 7 trong `AGENTS.md`: *RE-PLAN là một bounded strategy loop, không fix cứng fallback 5km -> 10km, không âm thầm nới lỏng hard constraints mà phải dựa trên bằng chứng lỗi có cấu trúc.*
   - Định nghĩa `ReplanAction` với các chiến lược thích ứng:
     - `suggest_budget_adjustment`: Khi toàn bộ ứng viên bị loại vì vượt ngân sách (`price_max`), tìm mức giá sàn thấp nhất hiện có quanh khu vực để gợi ý nới ngân sách chính xác hoặc gợi ý món rẻ hơn thay thế (bánh mì, xôi, cháo...).
     - `suggest_alternatives`: Khi toàn bộ ứng viên vi phạm kiêng kỵ nguyên liệu (`ingredient_exclude`), giải thích an toàn và đề xuất chuyển dòng món khác.
     - `expand_radius`: Khi không tìm thấy quán nào trong 5km ban đầu, đề xuất mở rộng lên 10km.
     - `suggest_combo_substitute`: Khi tìm combo cùng quán thất bại, đề xuất ưu tiên món chính rồi chọn nước có sẵn tại quán.
     - `clarify_concept`: Hỏi rõ thêm sở thích khi không còn phương án khả dĩ trong 10km.
2. **Tích hợp vào luồng thực thi & hiển thị (`agent/tools.py` & `services/recommendation.py`)**:
   - `tool_recommend_dishes_with_radius`: Khi `len(candidates) == 0`, tự động kích hoạt `diagnose_and_replan(...)` dựa trên `rejected_candidates` từ tầng VALIDATE.
   - `format_recommendations_output`: Định dạng banner chiến lược RE-PLAN (⚠️ **HỆ THỐNG ĐANG ĐIỀU CHỈNH KẾ HOẠCH (RE-PLAN)**) cực kỳ rõ ràng, trung thực, giải thích cặn kẽ nguyên nhân và đưa ra lời khuyên hành động.
3. **Kiểm thử tự động**:
   - Tạo bộ test độc lập [tests/test_replan.py](tests/test_replan.py) (4 tests).
   - Toàn bộ test suite **80/80 tests passed 100%**.

| File | Thay đổi |
|------|----------|
| `agent/replan.py` | Tạo mới module RE-PLAN chẩn đoán nguyên nhân thất bại và sinh ReplanAction |
| `agent/tools.py` | Kích hoạt `diagnose_and_replan` khi không còn ứng viên hợp lệ sau VALIDATE |
| `services/recommendation.py` | Hiển thị thông điệp chẩn đoán RE-PLAN thân thiện và minh bạch |
| `tests/test_replan.py` | Tạo mới 4 unit tests kiểm thử các kịch bản Replan |

---

## 📋 Component Status

| Component | Layer | Status | Notes |
|-----------|-------|--------|-------|
| `understand.py` | UNDERSTAND | 🚀 Active | LLM Qwen-3.8-27b chuyên sâu Food Delivery |
| `task_model.py` | Contract | ✅ Stable | Pydantic schema chuẩn (object/order) |
| `planner.py` | PLAN | 🚀 Upgraded | Semantic Category Mapping + Multi-Object Strategy |
| `tools.py` | ACT | 🚀 Upgraded | Nhận semantic_keywords & secondary_keywords |
| `services/search.py` | ACT | 🚀 Upgraded | Disambiguation ngữ nghĩa ẩm thực sâu + Secondary retrieval |
| `validator.py` | VALIDATE | 🚀 Upgraded | Kiểm tra hard constraints nghiêm ngặt + Sinh bằng chứng lỗi có cấu trúc |
| `replan.py` | RE-PLAN | 🚀 Active | Bounded strategy loop chẩn đoán lỗi & phản hồi thích ứng |
| `composer.py` | COMPOSE | 🚀 Upgraded | Ghép combo cùng quán + 1 lần phí ship + Validate ngân sách hậu kỳ |
| `services/recommendation.py` | RANK & RESPOND | 🚀 Upgraded | Chấm điểm cảm tính + Định dạng thẻ combo siêu trực quan |

---

### Session 10 (2026-09-24) — Kiến trúc Refactor theo Code Review

Thực hiện 6 fix ưu tiên cao từ Code Review chuyên sâu:

1. **Bug Fix: OpenAI Tool Schema** — Xóa `task_model` khỏi `required` của `get_user_preferences`. Thêm test validate tất cả tool schemas.
2. **Structured Output UNDERSTAND** — Bật `response_format=json_object`, fallback graceful, cải tiến `_parse_and_validate` (direct parse trước, regex chỉ là fallback).
3. **Profile Budget Separation** — `eff_budget=None` khi user không nói giá. Search rộng, VALIDATE enforce `price_max` từ TaskModel.
4. **Unified Orchestrator** — Xóa `_run_llm_loop()` (LLM tự do tool-calling). Thay bằng `_run_deterministic_pipeline()` duy nhất cho cả LLM và no-LLM mode. LLM chỉ được dùng tại UNDERSTAND + `_generate_llm_reply()`.
5. **RE-PLAN Execution Loop** — `expand_radius` tự động chạy lại `search_with_radius_expansion` (bounded: 1 retry) thay vì chỉ thông báo.
6. **Tests mới** — `tests/test_architecture_fixes.py` với **14 tests** cover toàn bộ fix trên.

| File | Thay đổi |
|------|----------|
| `agent/agent.py` | Viết lại: unified deterministic orchestrator |
| `agent/understand.py` | Structured Output + improved parse |
| `agent/tools.py` | Schema bug fix, profile budget separation, RE-PLAN execution |
| `tests/test_architecture_fixes.py` | Tạo mới 14 unit tests |

**Tổng: 95/95 tests passed (100%)**

---

## 📋 Component Status

| Component | Layer | Status | Notes |
|-----------|-------|--------|-------|
| `understand.py` | UNDERSTAND | 🚀 Upgraded | LLM + `response_format=json_object` + Regex Fallback |
| `task_model.py` | Contract | ✅ Stable | Pydantic schema chuẩn (object/order) |
| `agent.py` | Orchestrator | 🚀 Upgraded | **Unified Deterministic Pipeline** — LLM không còn tự do tool-calling |
| `planner.py` | PLAN | 🚀 Upgraded | Semantic Category Mapping + Multi-Object Strategy |
| `tools.py` | ACT | 🚀 Upgraded | Schema fixed, budget separation, RE-PLAN auto-execution |
| `services/search.py` | ACT | 🚀 Upgraded | Disambiguation ngữ nghĩa ẩm thực sâu + Secondary retrieval |
| `validator.py` | VALIDATE | 🚀 Upgraded | Hard constraints + Structured violation evidence |
| `replan.py` | RE-PLAN | 🚀 Upgraded | Bounded execution loop — auto-retry expand_radius |
| `composer.py` | COMPOSE | 🚀 Upgraded | Combo cùng quán + 1 lần phí ship + Budget post-composition |
| `services/recommendation.py` | RANK & RESPOND | 🚀 Upgraded | Semantic scoring + Combo cards + RE-PLAN banner |

---

### Session 11 (2026-09-24 → 2026-09-26) — Đánh giá pipeline & sửa 10 vấn đề hợp đồng
**Nhánh:** `fix/pipeline-contracts` — commit `f3cbd5d`, `4a2301e`, `212c233` (chưa push)

#### Vấn đề phát hiện (đánh giá toàn pipeline)
- Loại trừ món bằng substring: loại "gà" làm mất 52/204 món ("ngậy" → "ngay" chứa "ga"); "cơm" khớp "Combo".
- VALIDATE chạy **sau** khi cắt top-4 → mất món hợp lệ xếp hạng thấp.
- RESPOND nói điều không có trong dữ liệu ("chất lượng quán rất xứng đáng", ngân sách hồ sơ thay vì ngân sách user nói, "đã kiểm tra nguyên liệu" khi không có dữ liệu thành phần, nhãn "mở rộng 10km" sai).
- `follow_up`, `conversation_ref`, `party_size`, `strength` được trích xuất nhưng không tầng nào dùng.
- Dữ liệu crawl bị điền giá trị bịa (rating 4.7, khuyến mãi 15k từ chữ "Flash Sale", địa chỉ GrabFood gán theo thứ tự, giờ mở cửa 08–22).
- Geocoding: "Quận 10" bị tính là Quận 1; địa chỉ Hà Nội không rõ quận bị gán Cầu Giấy; địa chỉ mặc định "Cầu Giấy, Hà Nội" cài cứng ở 12 chỗ.
- RE-PLAN thực chất chỉ là 5km → 10km viết cứng (2 lần); tool `recommend_dishes_with_radius` ôm toàn bộ pipeline.
- Đơn nhiều món: 2 món chính chỉ ra 1 món; "có đồ uống ⇒ cùng quán" là suy luận không có căn cứ; ô không tên món (vd "đồ uống") không tìm được; frontend không hiển thị combo.
- Test suite xóa database thật `data/food_agent.db` mỗi lần chạy.
- `llama-3.3-70b-versatile` không còn trên Groq (mặc định của RESPOND).

#### Quyết định (đã chốt với user)
- `price_max` ("dưới 60k") tính theo **giá món** (giá menu × số phần, chưa ship, trước khuyến mãi).
- Model Groq mặc định: `qwen/qwen3.8-27b` (so sánh 14 câu UNDERSTAND: qwen 14/14 sau sửa schema, ~140 token; gpt-oss-120b 13/14, ~520 token, bị cắt JSON; gpt-oss-20b 9/14).
- **Không có địa chỉ mặc định**: user gõ địa chỉ (có quận) hoặc chọn trên bản đồ; thiếu thì PLAN hỏi lại.
- `same_order` ưu tiên một quán, không có quán nào đủ món thì **tách đơn** (mỗi quán 1 phí ship); `same_restaurant` chỉ khi user nói "cùng quán".

#### Thay đổi thực hiện
| File | Thay đổi |
|------|----------|
| `services/search.py` | `mentions_concept` (so khớp nguyên từ); `resolve_district` (nguyên từ, lấy quận xuất hiện cuối, không đoán từ tên thành phố); `estimate_distance` + `distance_basis`; tọa độ bản đồ; `search_within_radius` (1 lượt, không tự mở rộng, không lọc giá) thay `search_with_radius_expansion`; loader crawl không bịa dữ liệu |
| `agent/executor.py` | **Mới** — điều phối ACT → COMPOSE → RANK → VALIDATE → RE-PLAN, ghi `replan_trace` |
| `agent/replan.py` | Vòng `next_step` có giới hạn: mở rộng theo `radius_schedule` từ hồ sơ, rồi nới ẩm thực (chỉ khi còn gợi ý món); chẩn đoán follow-up, món không có ở đâu; đếm vi phạm theo ứng viên |
| `agent/planner.py` | `merge_follow_up`, `follow_up_constraints`, `location_clarification`, `composition_mode` |
| `agent/composer.py` | Viết lại: mỗi object là một ô, nhiều combo có giới hạn, tách đơn nhiều quán, `unavailable_objects`; bỏ kiểm tra ràng buộc cứng (VALIDATE lo) |
| `agent/validator.py` | Nguyên từ cho excluded concepts; `price_max` theo giá món; `follow_up_max_price`, `previously_shown` |
| `agent/agent.py` | Session state (task trước, món đã hiện) tách khỏi TaskModel; `provide_info` trả lời từ dữ liệu món được tham chiếu; lưu vị trí chỉ khi định vị được; chặn LLM đổi số liệu; sửa chit-chat trả lời nhầm tin trước |
| `agent/tools.py` | `recommend_dishes_with_radius` thành adapter mỏng; `set_user_location` |
| `agent/task_model.py` | `conversation_ref` nhận số thứ tự dạng số |
| `agent/understand.py` | `DEFAULT_GROQ_MODEL` dùng chung |
| `services/recommendation.py` | Validate trước top-k (`select_top_k`); ranking theo đúng thứ tự `priority_order` (gom nấc); lý do chỉ nêu dữ kiện truy vết được; nhãn ước tính; hiển thị tách đơn; `quantity` |
| `services/pricing.py` | `best_order_pricing` dùng chung |
| `database/models.py`, `database/db.py` | Bỏ địa chỉ mặc định; `latitude/longitude`; `estimated_fields`, `distance_basis`, `ingredients_source`, `restaurants`, `quantity` |
| `api.py` | Tọa độ trong chat/profile; `GET /api/locate`; 400 khi địa chỉ không định vị được |
| `static/*` | Chọn vị trí trên bản đồ (Leaflet + Esri tiles); bỏ mọi fallback bịa (rating 4.5, 20 phút, "Hà Nội", Cầu Giấy); thẻ combo/tách đơn, nút đặt theo từng quán |
| `tests/conftest.py` | Test dùng database tạm + địa chỉ test khai báo rõ |
| `tests/*` | Mới: `test_pipeline_regressions`, `test_follow_up`, `test_crawled_data`, `test_distance_and_ranking`, `test_location`, `test_replan_loop`, `test_composition` |

#### Kết quả
- **95 → 200 tests passed.** Đã chạy thử trên trình duyệt (Playwright): địa chỉ trống khi mở, chọn bản đồ, kết quả có nhãn "ước tính theo quận", thẻ tách đơn 2 quán.

#### Vấn đề tồn đọng
- Khoảng cách vẫn ở mức tâm quận; chính xác hơn cần geocoding thật (dịch vụ ngoài — chưa quyết).
- `semantic_attributes[].strength == "hard"` chưa được VALIDATE kiểm tra.
- Dữ liệu chỉ có 2 đồ uống → đơn "món + đồ uống" thường báo không có quán bán.
- Nguồn gốc `data/restaurants.json` và 20 quán Thanh Xuân (nhập tay trong `scripts/populate_thanhxuan_data.py`) chưa kiểm chứng.
- Esri tiles: ổn cho dự án cá nhân; thương mại cần xem điều khoản. `tile.openstreetmap.org` không phân giải DNS trên mạng hiện tại; CARTO đòi API key.
- Code chết: `OPENAI_TOOLS` + 5 tool cũ (~300 dòng).

#### Bổ sung (2026-09-26) — Thiết kế lại giao diện web
**Ý tưởng:** mỗi gợi ý là một **tờ hóa đơn quán** (tên quán in đầu, dòng món có chấm dẫn tới giá, phí ship, giảm giá, **Tổng** màu đỏ, mép giấy răng cưa, đánh "Số 1, Số 2…" — khớp với follow-up "món số 2 rẻ hơn"). Hóa đơn luôn **cộng đúng**: giảm giá = giá món + ship − tổng; freeship ghi ở dòng ship (không trừ 2 lần).

| Hạng mục | Chọn |
|------|----------|
| Màu | Gạch men `#E6ECF0` (nền), giấy `#FFFFFF`, mực `#1B2733`, xanh ghế nhựa `#1F5BD8` (hành động), đỏ biển hiệu `#D7261E` (tiêu đề, tổng), vàng tem `#FFD23F` (chỉ mã giảm giá) |
| Chữ | Be Vietnam Pro (chữ thường, số tabular) + Barlow Condensed (tiêu đề kiểu biển hiệu) |
| Bỏ | Nền tối + gradient, emoji dày đặc, chữ kỹ thuật ("SQLite Database", "Scale 10km"), welcome bị lặp giữa HTML và JS |

| File | Thay đổi |
|------|----------|
| `static/index.html` | Viết lại cấu trúc (giữ nguyên toàn bộ ID); thanh "Người nhận / Giao đến"; drawer & modal bản đồ gọn lại |
| `static/css/style.css` | Viết lại từ đầu (~600 dòng thay ~1650): hóa đơn, responsive tới 320px, focus rõ, `prefers-reduced-motion` |
| `static/js/app.js` | Render hóa đơn (`renderReceipt`), welcome 1 template, trace "Các bước đã chạy" dạng `<details>`, `aria-pressed` cho chip, nút xóa tag là `<button>`; nút đặt nói thật "chưa đặt trực tiếp được" |

**Trước khi đưa lên `main`:** đổi 27 link `file:///d:/...` (đường dẫn máy cá nhân, hỏng trên GitHub) thành link tương đối trong `README.md`, `PIPELINE_ARCHITECTURE.md`, `PROJECT_LOG.md`; bỏ tên cá nhân khỏi hồ sơ mẫu/giao diện/test (hồ sơ mẫu tên "Minh", ô tên không điền sẵn). `.env`, `*.db`, cache vẫn bị `.gitignore` chặn.

**Kiểm tra (Playwright):** không lỗi console; mọi hóa đơn cộng đúng tổng; không tràn ngang ở 390px và 320px (đã sửa 2 lỗi tràn: hàng chip quận, drawer ẩn); Tab đi đúng thứ tự. 200 tests vẫn pass.

---

## 📋 Component Status (sau Session 11)

| Component | Layer | Status | Notes |
|-----------|-------|--------|-------|
| `understand.py` | UNDERSTAND | ✅ Stable | Mặc định `qwen/qwen3.8-27b`; regex fallback |
| `task_model.py` | Contract | ✅ Stable | `conversation_ref` nhận số |
| `agent.py` | Orchestrator | 🚀 Upgraded | Session state, follow-up, hỏi vị trí, chặn LLM đổi số |
| `planner.py` | PLAN | 🚀 Upgraded | Follow-up merge/constraints, `composition_mode`, hỏi vị trí |
| `executor.py` | Orchestration | 🆕 New | Vòng ACT→COMPOSE→RANK→VALIDATE→RE-PLAN + trace |
| `tools.py` | ACT | 🚀 Refactored | Adapter mỏng; `set_user_location` |
| `services/search.py` | ACT | 🚀 Refactored | Tìm 1 bán kính; geocoding quận; không bịa dữ liệu crawl |
| `validator.py` | VALIDATE | 🚀 Upgraded | Nguyên từ, giá món, ràng buộc follow-up |
| `replan.py` | RE-PLAN | 🚀 Refactored | Vòng có giới hạn theo quan sát; không nới ràng buộc cứng |
| `composer.py` | COMPOSE | 🚀 Rewritten | Theo ô, nhiều combo, tách đơn nhiều quán |
| `services/recommendation.py` | RANK & RESPOND | 🚀 Upgraded | Ưu tiên theo thứ tự user; chỉ nêu dữ kiện có nguồn |

---

## 🔮 Next Priorities (Backlog)

0. **(Session 11)** Kiểm tra `strength: "hard"` cho semantic attributes; dọn `OPENAI_TOOLS` + tool cũ; bổ sung dữ liệu đồ uống; kiểm chứng nguồn dữ liệu seed.
1. **Giao diện người dùng (Rich Web UI / Streamlit / Chat Prototype)**: Demo trực quan luồng pipeline đầy đủ.
2. **Provenance & Freshness**: Bổ sung `data_source`, `crawled_at`, `confidence` vào `RecommendationCandidate`.
3. **Session Store**: Tách session state ra khỏi biến global trong `api.py`, hỗ trợ multi-worker.
4. **Fine-Tuning / SLM**: Gom log tương tác thành Dataset, fine-tune model 3B/7B chuyên biệt ẩm thực Việt.



