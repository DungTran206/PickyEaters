---
name: food-agent-testing
description: Build and run contract, regression, and agent-loop tests for the Personal Food Agent. Use when implementing features, fixing regressions, or validating architecture changes.
---

Test the system as a set of contracts, not only as example strings.

## Priority test layers

1. TaskModel contract tests
2. deterministic tool/service unit tests
3. Validate/Re-plan behavior tests
4. end-to-end agent-loop tests
5. anti-hallucination/provenance tests

## Minimum TaskModel matrix

Cover at least:

- "t muốn đồ nước" → Main + semantic attribute, not Drink
- "không muốn ăn cơm" → excluded_concepts, no positive rice object
- "40-80k muốn cơm với trà chanh" → two objects + same_order + both price bounds
- "2 người dưới 150k, không cay" → party_size=2 + total price_max=150000 + spicy=false
- "tối nay ăn gì nhẹ nhẹ?" → semantic attribute
- "cái này đắt quá, tìm cái khác" → follow-up + safe conversation reference
- ambiguous "cái này" with multiple candidates → conversation_ref=null
- "rẻ hơn nữa" → refine/lower-price semantics
- "tao ghét hành" → state_preference + ingredient exclusion
- "đói quá" → valid but under-specified TaskModel
- unsupported nuanced constraints → semantic_attributes, not invented enums
- impossible hard constraints → explicit validation/re-plan failure, never silent relaxation

## Regression principles

A regression test should assert semantic structure and important invariants, not fragile prose.

When a test fails:
- determine whether the contract is wrong, implementation is wrong, or the fixture is wrong;
- do not weaken the test merely to make CI green.

## Anti-hallucination checks

Where practical, assert that:
- prices come from tool data;
- distance comes from spatial calculations;
- ratings/promotions come from structured sources;
- final responses do not contain candidate facts absent from observations.

## Completion

Run focused tests first, then the full relevant suite. Report exact failures and do not claim success without actually running the tests.
