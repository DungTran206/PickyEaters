---
name: taskmodel-contract
description: Design, implement, validate, or review the Food Agent TaskModel contract and its structured-output tests. Use when changing intent extraction, constraints, objects, semantic attributes, relationships, follow-ups, or session references.
---

The TaskModel is the contract from UNDERSTAND to PLAN.

## Contract rules

- One user turn produces exactly one TaskModel.
- Unknown information stays null/empty.
- Do not invent defaults except schema-defined defaults such as party_size=1.
- Do not copy durable profile values into the current task unless explicitly stated.
- Negations must suppress positive object extraction for the negated concept.
- Price ranges preserve both bounds.
- Party size must not rewrite the budget.
- `ingredient_excludes` means ingredient-level exclusion.
- `excluded_concepts` means concept/category exclusion.
- `semantic_attributes` preserve open-ended language that has no suitable dedicated field.
- `relationships.objects` use zero-based object indices.
- `conversation_ref` can only be resolved from supplied last-shown ordinals.
- Never create candidate IDs in Understand.

## Important semantic distinction

"đồ nước" in this project refers to broth/liquid-based food, not beverages.

A safe representation is a Main object with an open semantic attribute such as `"đồ nước"`. Do not map it to `Drink`.

## When changing the schema

1. Identify the user capability that requires the change.
2. Check whether an existing open field (`semantic_attributes`, relationships) already represents it.
3. Add a dedicated field only when downstream behavior genuinely needs a stable structured value.
4. Update Pydantic/JSON Schema definitions and contract tests together.
5. Add positive, negative, ambiguous, and missing-information cases.

Avoid adding a new enum for every natural-language phrase.
