---
name: food-agent-code-review
description: Review Food Agent changes for architectural drift, semantic extraction bugs, data integrity, and test coverage. Use before merging or after Codex makes a substantial change.
---

Review changes in this order.

## 1. Architecture

Check that responsibilities remain:
Understand → TaskModel → Plan → Act → Observe → Validate → Re-plan → Compose → Rank → Respond.

Flag:
- raw text used downstream;
- NLU duplicated in fallback/mock code;
- large tools that combine retrieval, pricing, ranking, explanation, and formatting;
- hidden cross-layer dependencies.

## 2. TaskModel correctness

Check:
- negation;
- price ranges;
- party size;
- hard vs soft constraints;
- ingredient vs concept exclusions;
- open semantic attributes;
- object relationships;
- follow-up references;
- profile isolation.

Pay special attention to "đồ nước": it must not become Drink merely because the word contains "nước".

## 3. Data integrity

Flag:
- fabricated prices;
- fabricated addresses;
- guessed ratings;
- LLM-created candidate facts;
- scraper placeholders entering production retrieval.

## 4. Re-plan safety

Hard constraints must never be relaxed silently.

Changing radius, retrieval strategy, or soft preferences is acceptable when represented as an explicit bounded re-plan.

## 5. Tests

Require tests for the changed contract and relevant regressions.

## Review output

Report:
- blocking issues;
- important issues;
- minor issues;
- tests inspected/run.

Do not rewrite the code during review unless explicitly asked.
